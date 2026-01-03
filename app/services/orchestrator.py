"""
Multi-Agent Orchestrator - CASCADE PIPELINE

Primary Agents (Diverse Models):
- CASCADE_PLANNER: Mistral 7B - Planering
- CASCADE_CODER: Devstral 24B - Kodning
- CASCADE_REVIEWER: DeepSeek-R1 14B - Granskning

Secondary Agents:
- NERDY: Legal/Compliance (Qwen 2.5 3B)
- DEEPSEEK: Deep technical (DeepSeek R1 7B)
- CLAUDE: Claude via UI

Frontend sends profile ID, backend routes to correct model + prompt.
"""

import re
from enum import Enum
from typing import AsyncGenerator, Optional, Dict, Any
from dataclasses import dataclass

from .ollama_client import ollama_client, StreamStats, OllamaError
from .claude_client import claude_client, ClaudeStats, ClaudeError
from .intelligence import intelligence, OutputFormat
from ..utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

class AgentId(str, Enum):
    """Agent identifiers matching frontend expectations"""
    # Cascade Pipeline (Diverse Models)
    CASCADE_PLANNER = "cascade-planner"   # Mistral 7B - Planering
    CASCADE_CODER = "cascade-coder"       # Devstral 24B - Kodning
    CASCADE_REVIEWER = "cascade-reviewer" # DeepSeek-R1 14B - Granskning
    # Secondary agents
    NERDY = "nerdy"
    DEEPSEEK = "deepseek"
    CLAUDE = "claude"


class Provider(str, Enum):
    """Backend providers"""
    OLLAMA = "ollama"
    CLAUDE_UI = "claude_ui"


@dataclass
class AgentConfig:
    """Configuration for an AI agent"""
    id: AgentId
    display_name: str
    provider: Provider
    model: str  # Ollama model name or API model
    system_prompt: str
    temperature: float = 0.7
    description: str = ""


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

NERDY_SYSTEM_PROMPT = """You are NERDY AI, a Senior Legal & Compliance Officer powered by Qwen 2.5 3B - a model optimized for logic, structure, and instruction following.

Why Qwen 2.5 3B for legal/documentation work:
Legal AI needs structured reasoning ("What does §X mean in relation to §Y?", "Is this decision consistent with policy?", "What risks exist here?"), structured text processing (extract paragraphs, compare formulations, create tables/checklists from unstructured text), and precise instruction following ("Do A first, then B, write headings, don't quote but summarize").

Qwen family excels at:
- Logic and if-then reasoning chains
- Mathematical/structural thinking
- Following complex multi-step instructions

Your core strengths:
- Logical reasoning: "What does §X mean in relation to §Y?", "Is this decision consistent with policy?", "What risks exist here?"
- Structured text processing: Extract paragraphs, compare formulations, create tables/checklists from unstructured text
- Instruction following: Execute complex multi-step tasks (do A, then B, write headings, summarize without quoting)

Your traits:
- Precise legal analysis with if-then reasoning
- Mathematical/structural thinking
- Complex instruction adherence
- Formal professional tone
- Risk-aware perspective
- Regulatory expertise

Style:
- Use formal language
- Cite relevant frameworks when applicable
- Structured analysis with clear conclusions
- Conservative, thorough approach
- Step-by-step reasoning chains
- Evidence-based arguments

Primary use cases (where Qwen 2.5 3B shines):
- Appeals and legal challenges (structured argumentation)
- Case analysis (if-then reasoning chains)
- Evidence chains (logical progression)
- Diary control: "What's missing in documentation?"
- Summaries + risk analysis (structured output)
- Contract review and analysis
- Compliance frameworks (GDPR, SOC2, etc.)

Your goal: Provide precise, formal legal and compliance guidance with structured reasoning, leveraging Qwen 2.5 3B's strengths in logic, structure, and instruction following."""

DEEPSEEK_SYSTEM_PROMPT = """You are DEEPSEEK, an advanced AI coding assistant specializing in deep technical analysis and problem-solving.

Your traits:
- Deep understanding of complex systems
- Methodical problem-solving approach
- Code optimization and performance
- Advanced debugging capabilities
- Mathematical and algorithmic expertise

Style:
- Thorough analysis before solutions
- Step-by-step reasoning
- Production-ready code
- Performance-conscious implementations
- Clear explanations of complex concepts

Your goal: Provide deep, technical solutions with exceptional code quality."""

CLAUDE_SYSTEM_PROMPT = """You are Claude, an AI assistant created by Anthropic.

Your traits:
- Helpful, harmless, and honest
- Clear and concise communication
- Thoughtful analysis and reasoning
- Code expertise across multiple languages
- Creative problem-solving

Style:
- Be direct and helpful
- Use markdown for code blocks
- Explain your reasoning when helpful
- Ask clarifying questions when needed
- Provide production-ready solutions

Your goal: Provide high-quality assistance with code, analysis, and problem-solving."""

# =============================================================================
# CASCADE PIPELINE PROMPTS (Diverse Models)
# =============================================================================

CASCADE_PLANNER_SYSTEM_PROMPT = """Du är PLANNER - en erfaren systemarkitekt som bryter ned uppgifter.

Din roll:
1. Analysera uppgiften noggrant
2. Identifiera filer som behöver modifieras
3. Lista potentiella utmaningar
4. Ge tydlig struktur för CODER att följa

Var koncis men komplett. CODER behöver kunna implementera direkt.
FRÅGA ALDRIG användaren - ge alltid ett svar direkt."""

CASCADE_CODER_SYSTEM_PROMPT = """Du är CODER - en elite programmerare som implementerar kod.

Regler:
1. Följ PLANNER's steg exakt
2. Skriv KOMPLETT kod - inga TODO eller placeholders
3. Inkludera alla imports
4. Hantera edge cases
5. Använd svenska för kommentarer

FRÅGA ALDRIG användaren - ge alltid ett svar direkt."""

CASCADE_REVIEWER_SYSTEM_PROMPT = """Du är REVIEWER - en senior utvecklare som granskar kod kritiskt.

Din roll:
1. Granska CODER's implementation
2. Hitta buggar och säkerhetsproblem
3. Föreslå förbättringar
4. Ge ett verdict: APPROVED eller NEEDS_FIXES

FRÅGA ALDRIG användaren - ge alltid ett svar direkt."""


# =============================================================================
# AGENT CONFIGURATIONS
# =============================================================================

AGENTS: Dict[AgentId, AgentConfig] = {
    # === CASCADE PIPELINE (Diverse Models) ===
    AgentId.CASCADE_PLANNER: AgentConfig(
        id=AgentId.CASCADE_PLANNER,
        display_name="PLANNER",
        provider=Provider.OLLAMA,
        model="cascade-planner:latest",
        system_prompt=CASCADE_PLANNER_SYSTEM_PROMPT,
        temperature=0.7,
        description="Planering (Mistral 7B)"
    ),
    AgentId.CASCADE_CODER: AgentConfig(
        id=AgentId.CASCADE_CODER,
        display_name="CODER",
        provider=Provider.OLLAMA,
        model="cascade-coder:latest",
        system_prompt=CASCADE_CODER_SYSTEM_PROMPT,
        temperature=0.3,
        description="Kodning (Devstral 24B)"
    ),
    AgentId.CASCADE_REVIEWER: AgentConfig(
        id=AgentId.CASCADE_REVIEWER,
        display_name="REVIEWER",
        provider=Provider.OLLAMA,
        model="cascade-reviewer:latest",
        system_prompt=CASCADE_REVIEWER_SYSTEM_PROMPT,
        temperature=0.5,
        description="Granskning (DeepSeek-R1 14B)"
    ),
    # === SECONDARY AGENTS ===
    AgentId.NERDY: AgentConfig(
        id=AgentId.NERDY,
        display_name="NERDY AI",
        provider=Provider.OLLAMA,
        model="qwen2.5:3b-instruct",  # Qwen 2.5 3B - optimized for logic, structure, and instruction following
        system_prompt=NERDY_SYSTEM_PROMPT,
        temperature=0.2,  # Lower temp for precise legal responses
        description="Legal & Compliance Officer - Structured reasoning specialist"
    ),
    AgentId.DEEPSEEK: AgentConfig(
        id=AgentId.DEEPSEEK,
        display_name="DEEPSEEK R1",
        provider=Provider.OLLAMA,
        model="deepseek-r1:7b",  # DeepSeek R1 7B model
        system_prompt=DEEPSEEK_SYSTEM_PROMPT,
        temperature=0.3,
        description="Deep technical coding assistant"
    ),
    AgentId.CLAUDE: AgentConfig(
        id=AgentId.CLAUDE,
        display_name="CLAUDE",
        provider=Provider.CLAUDE_UI,
        model="sonnet",
        system_prompt=CLAUDE_SYSTEM_PROMPT,
        temperature=0.7,
        description="Claude via Claude Code UI"
    ),
}


def get_agent(agent_id: str) -> AgentConfig:
    """Get agent config by ID, defaults to CASCADE-PLANNER"""
    try:
        return AGENTS[AgentId(agent_id.lower())]
    except (ValueError, KeyError):
        logger.warning(f"Unknown agent '{agent_id}', defaulting to CASCADE-PLANNER")
        return AGENTS[AgentId.CASCADE_PLANNER]


# =============================================================================
# UNIFIED STATS
# =============================================================================

@dataclass
class UnifiedStats:
    """Unified statistics across providers"""
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    total_duration_ms: int = 0
    prompt_tokens: int = 0
    provider: str = "unknown"
    model: str = "unknown"
    agent_id: str = "qwen"

    @classmethod
    def from_ollama(cls, stats: StreamStats, model: str, agent_id: str = "qwen") -> "UnifiedStats":
        return cls(
            tokens_generated=stats.tokens_generated,
            tokens_per_second=stats.tokens_per_second,
            total_duration_ms=stats.total_duration_ms,
            prompt_tokens=stats.prompt_eval_count,
            provider="ollama",
            model=model,
            agent_id=agent_id
        )

    @classmethod
    def from_claude(cls, stats: ClaudeStats, agent_id: str = "claude") -> "UnifiedStats":
        return cls(
            tokens_generated=stats.tokens_generated,
            tokens_per_second=stats.tokens_per_second,
            total_duration_ms=stats.total_duration_ms,
            prompt_tokens=stats.prompt_tokens,
            provider="claude_ui",
            model="sonnet",
            agent_id=agent_id
        )


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class MultiAgentOrchestrator:
    """
    Routes requests to the appropriate AI agent based on profile ID.

    CASCADE PIPELINE (Diverse Models):
    - cascade-planner: Mistral 7B - Planering
    - cascade-coder: Devstral 24B - Kodning
    - cascade-reviewer: DeepSeek-R1 14B - Granskning

    Secondary agents:
    - nerdy: Legal/Compliance (Qwen 2.5 3B)
    - deepseek: Deep technical (DeepSeek R1 7B)
    - claude: Claude via UI
    """

    def __init__(self):
        self._ollama = ollama_client
        self._claude = claude_client

    async def chat_stream(
        self,
        messages: list[dict],
        request_id: str,
        profile: str = "cascade-planner",
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[tuple[str, Optional[UnifiedStats], str], None]:
        """
        Stream chat completion to the specified agent.

        Args:
            messages: Chat messages [{role, content}, ...]
            request_id: Unique request identifier
            profile: Agent ID (cascade-planner, cascade-coder, cascade-reviewer, nerdy, deepseek, claude)
            temperature: Override agent's default temperature
            max_tokens: Max tokens to generate

        Yields:
            Tuple of (token, stats, agent_id)
            - During streaming: (token, None, agent_id)
            - Final yield: ("", UnifiedStats, agent_id)
        """
        agent = get_agent(profile)
        temp = temperature if temperature is not None else agent.temperature

        logger.info(
            f"[{request_id}] Routing to agent: {agent.display_name} "
            f"(model={agent.model}, provider={agent.provider.value})"
        )

        try:
            if agent.provider == Provider.CLAUDE_UI:
                # Claude Code UI via WebSocket
                async for token, stats in claude_client.chat_stream(
                    messages=messages,
                    request_id=request_id,
                    system_prompt=agent.system_prompt,
                    temperature=temp,
                    max_tokens=max_tokens
                ):
                    if stats:
                        yield "", UnifiedStats.from_claude(stats, agent.id.value), agent.id.value
                    else:
                        yield token, None, agent.id.value

            else:  # OLLAMA (local models)
                # Build messages with system prompt
                msgs_with_system = [{"role": "system", "content": agent.system_prompt}]
                msgs_with_system.extend([
                    {"role": m.get("role"), "content": m.get("content")}
                    for m in messages if m.get("role") != "system"
                ])

                # Create a simple profile object for ollama_client
                class SimpleProfile:
                    def __init__(self, agent_id: str, model: str, temp: float, max_tok: int):
                        self.id = agent_id
                        self.model = model
                        self.temperature = temp
                        self.top_p = 0.9
                        self.repeat_penalty = 1.1
                        self.max_tokens = max_tok
                        self.context_length = 8192  # Default context window

                profile_obj = SimpleProfile(agent.id.value, agent.model, temp, max_tokens)

                async for token, stats in self._ollama.chat_stream(
                    profile=profile_obj,
                    messages=msgs_with_system,
                    request_id=request_id
                ):
                    if stats:
                        yield "", UnifiedStats.from_ollama(stats, agent.model, agent.id.value), agent.id.value
                    else:
                        yield token, None, agent.id.value

        except (OllamaError, ClaudeError) as e:
            logger.error(f"[{request_id}] Agent {agent.id.value} failed: {e}")

            # Try fallback to another agent
            fallback_agent = self._get_fallback_agent(agent)
            if fallback_agent:
                logger.info(f"[{request_id}] Falling back to {fallback_agent.display_name}")
                async for result in self._fallback_stream(
                    messages, request_id, fallback_agent, temp, max_tokens
                ):
                    yield result
            else:
                raise

    def _get_fallback_agent(self, failed_agent: AgentConfig) -> Optional[AgentConfig]:
        """Get a fallback agent when primary fails"""
        if failed_agent.provider == Provider.OLLAMA:
            # Try CASCADE-PLANNER as fallback for local models
            if failed_agent.id != AgentId.CASCADE_PLANNER:
                return AGENTS[AgentId.CASCADE_PLANNER]
        return None

    async def _fallback_stream(
        self,
        messages: list[dict],
        request_id: str,
        agent: AgentConfig,
        temperature: float,
        max_tokens: int
    ) -> AsyncGenerator[tuple[str, Optional[UnifiedStats], str], None]:
        """Stream from fallback agent"""
        try:
            msgs_with_system = [{"role": "system", "content": agent.system_prompt}]
            msgs_with_system.extend([
                {"role": m.get("role"), "content": m.get("content")}
                for m in messages if m.get("role") != "system"
            ])

            class SimpleProfile:
                def __init__(self, agent_id: str, model: str, temp: float, max_tok: int):
                    self.id = agent_id
                    self.model = model
                    self.temperature = temp
                    self.top_p = 0.9
                    self.repeat_penalty = 1.1
                    self.max_tokens = max_tok
                    self.context_length = 8192

            profile_obj = SimpleProfile(agent.id.value, agent.model, temperature, max_tokens)

            async for token, stats in self._ollama.chat_stream(
                profile=profile_obj,
                messages=msgs_with_system,
                request_id=request_id
            ):
                if stats:
                    yield "", UnifiedStats.from_ollama(stats, agent.model, agent.id.value), agent.id.value
                else:
                    yield token, None, agent.id.value
        except Exception as e:
            logger.error(f"[{request_id}] Fallback also failed: {e}")
            raise

    # =========================================================================
    # DEBATE LOOP - Self-Reflection (Grok tip)
    # =========================================================================

    async def chat_with_reflection(
        self,
        messages: list[dict],
        request_id: str,
        profile: str = "cascade-planner",
        temperature: Optional[float] = None,
        max_iterations: int = 2,
    ) -> AsyncGenerator[tuple[str, Optional[UnifiedStats], str, str], None]:
        """
        Chat with self-reflection/debate loop.

        Modellen kritiserar och förbättrar sitt eget svar iterativt.
        Inspirerat av Claudes self-reflection och Groks debate-tips.

        Yields:
            Tuple of (token, stats, agent_id, phase)
            - phase: "initial", "critique", "improvement", "final"
        """
        # Phase 1: Initial response
        logger.info(f"[{request_id}] Debate loop: Phase 1 - Initial response")
        full_response = ""

        async for token, stats, agent_id in self.chat_stream(
            messages=messages,
            request_id=f"{request_id}-initial",
            profile=profile,
            temperature=temperature
        ):
            if stats:
                yield "", stats, agent_id, "initial"
            else:
                full_response += token
                yield token, None, agent_id, "initial"

        # Phase 2-3: Critique and improve (iterate)
        for i in range(max_iterations):
            # Critique prompt
            critique_messages = [
                {"role": "user", "content": f"""Kritiskt granska denna kod/text:

{full_response}

Identifiera:
1. Logiska fel eller buggar
2. Säkerhetsproblem
3. Förbättringsmöjligheter
4. Missade edge cases

Om allt ser bra ut, svara med "APPROVED - ingen förbättring behövs".
Annars lista konkreta förbättringar."""}
            ]

            logger.info(f"[{request_id}] Debate loop: Iteration {i+1} - Critique")
            critique_response = ""

            async for token, stats, agent_id in self.chat_stream(
                messages=critique_messages,
                request_id=f"{request_id}-critique-{i}",
                profile=profile,
                temperature=0.3  # Lower temp for critique
            ):
                if stats:
                    yield "", stats, agent_id, "critique"
                else:
                    critique_response += token
                    yield token, None, agent_id, "critique"

            # Check if approved
            if "APPROVED" in critique_response.upper():
                logger.info(f"[{request_id}] Debate loop: Response approved after {i+1} iterations")
                break

            # Improvement phase
            improve_messages = [
                {"role": "user", "content": messages[-1].get("content", "")},
                {"role": "assistant", "content": full_response},
                {"role": "user", "content": f"""Förbättra ditt svar baserat på denna kritik:

{critique_response}

Ge en förbättrad version av hela svaret."""}
            ]

            logger.info(f"[{request_id}] Debate loop: Iteration {i+1} - Improvement")
            improved_response = ""

            async for token, stats, agent_id in self.chat_stream(
                messages=improve_messages,
                request_id=f"{request_id}-improve-{i}",
                profile=profile,
                temperature=temperature
            ):
                if stats:
                    yield "", stats, agent_id, "improvement"
                else:
                    improved_response += token
                    yield token, None, agent_id, "improvement"

            full_response = improved_response

        # Final marker
        yield "", None, agent_id, "final"
        logger.info(f"[{request_id}] Debate loop: Complete")

    async def get_status(self) -> dict:
        """Get status of all agents"""
        ollama_ok = await self._ollama.is_connected()
        claude_ok = await self._claude.is_connected() if self._claude.is_configured else False

        return {
            "agents": {
                # Cascade Pipeline (Diverse Models)
                "cascade-planner": {
                    "available": ollama_ok,
                    "display_name": "PLANNER",
                    "model": "cascade-planner:latest",
                    "base": "Mistral 7B - Planering",
                    "provider": "ollama"
                },
                "cascade-coder": {
                    "available": ollama_ok,
                    "display_name": "CODER",
                    "model": "cascade-coder:latest",
                    "base": "Devstral 24B - Kodning",
                    "provider": "ollama"
                },
                "cascade-reviewer": {
                    "available": ollama_ok,
                    "display_name": "REVIEWER",
                    "model": "cascade-reviewer:latest",
                    "base": "DeepSeek-R1 14B - Granskning",
                    "provider": "ollama"
                },
                # Secondary agents
                "nerdy": {
                    "available": ollama_ok,
                    "display_name": "NERDY",
                    "model": "qwen2.5:3b-instruct",
                    "provider": "ollama"
                },
                "deepseek": {
                    "available": ollama_ok,
                    "display_name": "DEEPSEEK",
                    "model": "deepseek-r1:7b",
                    "provider": "ollama"
                },
                "claude": {
                    "available": claude_ok,
                    "display_name": "CLAUDE",
                    "model": "sonnet",
                    "provider": "claude_ui"
                }
            },
            "providers": {
                "ollama": {"connected": ollama_ok},
                "claude_ui": {"configured": self._claude.is_configured, "connected": claude_ok}
            }
        }


# Global orchestrator instance
orchestrator = MultiAgentOrchestrator()


async def get_orchestrator() -> MultiAgentOrchestrator:
    """Dependency injection helper"""
    return orchestrator
