"""
Agent Lightning Integration för Cascade Pipeline
=================================================
LitAgent-wrapper som möjliggör RL-träning av Planner→Coder→Reviewer.

Använder Microsoft Agent Lightning för att:
- Samla traces från cascade-körningar
- Beräkna rewards baserat på kodkvalitet
- Träna modellerna med reinforcement learning

Kräver: pip install agentlightning
"""

import asyncio
import re
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from agentlightning import LitAgent

from .cascade_orchestrator import (
    cascade_orchestrator,
    CascadePhase,
    CascadeResult
)
from .ollama_client import ollama_client
from ..utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# REWARD FUNCTIONS
# =============================================================================

@dataclass
class RewardSignals:
    """Reward signals från en cascade-körning"""
    # Planning rewards
    has_clear_steps: float = 0.0
    has_file_list: float = 0.0
    has_challenges: float = 0.0

    # Coding rewards
    has_code_blocks: float = 0.0
    code_is_complete: float = 0.0
    has_imports: float = 0.0
    no_placeholders: float = 0.0

    # Review rewards
    has_bug_section: float = 0.0
    has_verdict: float = 0.0
    is_approved: float = 0.0

    # Overall
    task_completed: float = 0.0

    def total(self) -> float:
        """Beräkna total reward (-1 till +3 skala)"""
        weights = {
            # Planning (max 0.6)
            'has_clear_steps': 0.2,
            'has_file_list': 0.2,
            'has_challenges': 0.2,

            # Coding (max 1.2)
            'has_code_blocks': 0.3,
            'code_is_complete': 0.4,
            'has_imports': 0.2,
            'no_placeholders': 0.3,

            # Review (max 0.6)
            'has_bug_section': 0.2,
            'has_verdict': 0.2,
            'is_approved': 0.2,

            # Completion (max 0.6)
            'task_completed': 0.6,
        }

        total = sum(
            getattr(self, key) * weight
            for key, weight in weights.items()
        )

        return min(3.0, max(-1.0, total))


def analyze_plan(content: str) -> Dict[str, float]:
    """Analysera planner output för reward signals"""
    signals = {}

    # Kolla efter tydliga steg
    step_patterns = [
        r'##\s*IMPLEMENTATION\s*STEG',
        r'##\s*STEG',
        r'\d+\.\s+\[?Steg',
        r'1\.\s+\w+',
    ]
    signals['has_clear_steps'] = 1.0 if any(
        re.search(p, content, re.IGNORECASE) for p in step_patterns
    ) else 0.0

    # Kolla efter fillista
    file_patterns = [
        r'##\s*FILER',
        r'- \[?\w+\.(py|ts|js|tsx|jsx)\]?',
        r'`\w+\.\w+`',
    ]
    signals['has_file_list'] = 1.0 if any(
        re.search(p, content, re.IGNORECASE) for p in file_patterns
    ) else 0.0

    # Kolla efter utmaningar
    challenge_patterns = [
        r'##\s*(POTENTIELLA\s*)?UTMANINGAR',
        r'##\s*RISKER',
        r'OBS:',
        r'Utmaning:',
    ]
    signals['has_challenges'] = 1.0 if any(
        re.search(p, content, re.IGNORECASE) for p in challenge_patterns
    ) else 0.0

    return signals


def analyze_code(content: str) -> Dict[str, float]:
    """Analysera coder output för reward signals"""
    signals = {}

    # Kolla efter kodblock
    code_blocks = re.findall(r'```[\w]*\n[\s\S]*?\n```', content)
    signals['has_code_blocks'] = min(1.0, len(code_blocks) * 0.25)

    # Kolla om koden ser komplett ut
    completeness_signals = [
        r'def\s+\w+\s*\(',  # Funktioner
        r'class\s+\w+',     # Klasser
        r'return\s+',       # Return statements
        r'if\s+__name__',   # Main guard
    ]
    completeness_score = sum(
        1 for p in completeness_signals if re.search(p, content)
    ) / len(completeness_signals)
    signals['code_is_complete'] = completeness_score

    # Kolla efter imports
    signals['has_imports'] = 1.0 if re.search(
        r'(import\s+\w+|from\s+\w+\s+import)', content
    ) else 0.0

    # Negativ: placeholders
    placeholder_patterns = [
        r'#\s*\.\.\.',
        r'//\s*\.\.\.',
        r'pass\s*#\s*TODO',
        r'\.\.\.\s*resten',
        r'# Add your code here',
    ]
    has_placeholders = any(
        re.search(p, content, re.IGNORECASE) for p in placeholder_patterns
    )
    signals['no_placeholders'] = 0.0 if has_placeholders else 1.0

    return signals


def analyze_review(content: str) -> Dict[str, float]:
    """Analysera reviewer output för reward signals"""
    signals = {}

    # Kolla efter bug-sektion
    signals['has_bug_section'] = 1.0 if re.search(
        r'##\s*(BUGGAR|BUGS|FEL)', content, re.IGNORECASE
    ) else 0.0

    # Kolla efter verdict
    signals['has_verdict'] = 1.0 if re.search(
        r'##\s*VERDICT|APPROVED|NEEDS\s*CHANGES', content, re.IGNORECASE
    ) else 0.0

    # Kolla om approved
    if re.search(r'APPROVED\s*[✓✔]', content, re.IGNORECASE):
        signals['is_approved'] = 1.0
    elif re.search(r'NEEDS\s*CHANGES\s*[✗✘]', content, re.IGNORECASE):
        signals['is_approved'] = 0.3  # Partial credit för att hitta problem
    else:
        signals['is_approved'] = 0.0

    return signals


# =============================================================================
# LIT AGENT IMPLEMENTATION
# =============================================================================

class CascadeLitAgent(LitAgent):
    """
    LitAgent wrapper för Cascade Orchestrator.

    Möjliggör RL-träning av multi-agent cascade genom att:
    1. Köra cascade på training tasks
    2. Samla output från varje fas
    3. Beräkna reward baserat på output-kvalitet
    4. Returnera reward för GRPO/PPO training

    Användning:
        agent = CascadeLitAgent()
        await agent.training_rollout_async(task, rollout_id, resources)
    """

    def __init__(self):
        super().__init__()
        self.cascade = cascade_orchestrator
        self.ollama = ollama_client
        logger.info("CascadeLitAgent initialized")

    async def training_rollout_async(
        self,
        task: Dict[str, Any],
        rollout_id: str,
        resources: Optional[Dict] = None
    ) -> float:
        """
        Huvudträningsloop - kör cascade och beräkna reward.

        Args:
            task: Training task med "question" och optional "expected_answer"
            rollout_id: Unik ID för denna rollout
            resources: Tillgängliga resurser (ignoreras för nu)

        Returns:
            reward: Float mellan -1 och +3
        """
        logger.info(f"[{rollout_id}] Starting training rollout")

        # Extrahera task
        question = task.get("question", task.get("task", ""))
        expected = task.get("expected_answer", task.get("expected", ""))
        skip_review = task.get("skip_review", False)

        if not question:
            logger.error(f"[{rollout_id}] Empty question in task")
            return -1.0

        # Samla output från cascade
        plan_content = ""
        code_content = ""
        review_content = ""
        completed = False

        try:
            async for result in self.cascade.execute_cascade(
                task=question,
                request_id=rollout_id,
                skip_review=skip_review
            ):
                if result.phase == CascadePhase.PLANNING:
                    plan_content += result.content
                elif result.phase == CascadePhase.CODING:
                    code_content += result.content
                elif result.phase == CascadePhase.REVIEWING:
                    review_content += result.content
                elif result.phase == CascadePhase.COMPLETE:
                    completed = True

        except Exception as e:
            logger.error(f"[{rollout_id}] Cascade failed: {e}")
            return -1.0

        # Beräkna reward signals
        signals = RewardSignals()

        # Planning signals
        if plan_content:
            plan_signals = analyze_plan(plan_content)
            signals.has_clear_steps = plan_signals.get('has_clear_steps', 0)
            signals.has_file_list = plan_signals.get('has_file_list', 0)
            signals.has_challenges = plan_signals.get('has_challenges', 0)

        # Coding signals
        if code_content:
            code_signals = analyze_code(code_content)
            signals.has_code_blocks = code_signals.get('has_code_blocks', 0)
            signals.code_is_complete = code_signals.get('code_is_complete', 0)
            signals.has_imports = code_signals.get('has_imports', 0)
            signals.no_placeholders = code_signals.get('no_placeholders', 0)

        # Review signals
        if review_content:
            review_signals = analyze_review(review_content)
            signals.has_bug_section = review_signals.get('has_bug_section', 0)
            signals.has_verdict = review_signals.get('has_verdict', 0)
            signals.is_approved = review_signals.get('is_approved', 0)

        # Completion bonus
        signals.task_completed = 1.0 if completed else 0.0

        # Extra reward för match mot expected (om tillgängligt)
        if expected and code_content:
            # Simple keyword matching
            expected_keywords = set(re.findall(r'\w{4,}', expected.lower()))
            code_keywords = set(re.findall(r'\w{4,}', code_content.lower()))
            if expected_keywords:
                overlap = len(expected_keywords & code_keywords) / len(expected_keywords)
                signals.task_completed += overlap * 0.5

        # Beräkna total reward
        reward = signals.total()

        logger.info(
            f"[{rollout_id}] Rollout complete - "
            f"reward={reward:.2f}, "
            f"plan={len(plan_content)}, code={len(code_content)}, "
            f"review={len(review_content)}"
        )

        return reward

    async def inference_async(
        self,
        task: Dict[str, Any],
        request_id: str
    ) -> Dict[str, str]:
        """
        Inference mode (ej träning) - returnera cascade output.

        Args:
            task: Task att köra
            request_id: Request ID

        Returns:
            {"plan": "...", "code": "...", "review": "..."}
        """
        return await self.cascade.quick_cascade(
            task=task.get("question", task.get("task", "")),
            request_id=request_id
        )


# =============================================================================
# TRAINING SCRIPT HELPERS
# =============================================================================

async def run_training_episode(
    agent: CascadeLitAgent,
    tasks: List[Dict[str, Any]],
    episode_id: str
) -> List[float]:
    """
    Kör en träningsepisode med flera tasks.

    Args:
        agent: CascadeLitAgent instance
        tasks: Lista med training tasks
        episode_id: Episode identifier

    Returns:
        Lista med rewards för varje task
    """
    rewards = []

    for i, task in enumerate(tasks):
        rollout_id = f"{episode_id}-task{i}"
        logger.info(f"Running task {i+1}/{len(tasks)}: {rollout_id}")

        reward = await agent.training_rollout_async(
            task=task,
            rollout_id=rollout_id,
            resources=None
        )
        rewards.append(reward)

        logger.info(f"Task {i+1} reward: {reward:.2f}")

    avg_reward = sum(rewards) / len(rewards) if rewards else 0
    logger.info(f"Episode {episode_id} complete - avg reward: {avg_reward:.2f}")

    return rewards


def load_training_tasks(path: str) -> List[Dict[str, Any]]:
    """Ladda training tasks från JSONL fil"""
    import json

    tasks = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                # Konvertera till task-format
                tasks.append({
                    "question": data.get("instruction", ""),
                    "expected_answer": data.get("output", ""),
                })

    return tasks


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

cascade_lit_agent = CascadeLitAgent()


def get_cascade_lit_agent() -> CascadeLitAgent:
    """Dependency injection helper"""
    return cascade_lit_agent
