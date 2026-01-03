"""
Multi-Agent Cascade Orchestrator
================================
Implementerar Grok's tips: Planner → Coder → Reviewer pipeline.

3-stegs agent-kedja där varje agent har en specifik roll:
1. PLANNER - Analyserar uppgift, bryter ned i steg
2. CODER - Implementerar kod baserat på plan
3. REVIEWER - Granskar koden, hittar buggar

Hot-swap mellan modeller för att spara VRAM (RTX 4070 = 12GB).
"""

from typing import AsyncGenerator, Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from .ollama_client import ollama_client
from .orchestrator import orchestrator, UnifiedStats
from ..utils.logging import get_logger

logger = get_logger(__name__)


class CascadePhase(str, Enum):
    """Faser i cascade-pipelinen"""
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    COMPLETE = "complete"


@dataclass
class CascadeResult:
    """Resultat från en cascade-fas"""
    phase: CascadePhase
    agent_id: str
    content: str
    stats: Optional[UnifiedStats] = None


# =============================================================================
# SYSTEM PROMPTS FÖR VARJE ROLL
# =============================================================================

PLANNER_SYSTEM_PROMPT = """Du är PLANNER - en erfaren systemarkitekt som bryter ned uppgifter.

DIN ROLL:
1. Analysera användarens uppgift noggrant
2. Bryt ned i konkreta implementeringssteg
3. Identifiera potentiella utmaningar
4. Ge tydlig struktur för CODER att följa

OUTPUT FORMAT:
## ANALYS
[Kort sammanfattning av vad som ska byggas]

## IMPLEMENTATION STEG
1. [Steg 1 - konkret och actionable]
2. [Steg 2]
...

## FILER ATT SKAPA/ÄNDRA
- [fil1.py] - [syfte]
- [fil2.py] - [syfte]

## POTENTIELLA UTMANINGAR
- [Utmaning 1]
- [Utmaning 2]

Var koncis men komplett. CODER behöver kunna implementera direkt."""

CODER_SYSTEM_PROMPT = """Du är CODER - en elite programmerare som implementerar kod.

DIN ROLL:
1. Följ PLANNER's steg exakt
2. Skriv produktionsklar kod
3. Inkludera felhantering
4. Följ De 4 Reglerna

REGLER:
- KOD FÖRST - minimal text, max en mening mellan kodblock
- HELA FILER - aldrig "// ..." eller "resten av koden"
- INGA EMOJIS I KOD
- Inkludera imports och alla dependencies

Du får en PLAN från PLANNER. Implementera varje steg med faktisk kod."""

REVIEWER_SYSTEM_PROMPT = """Du är REVIEWER - en senior utvecklare som granskar kod kritiskt.

DIN ROLL:
1. Granska CODER's implementation
2. Hitta buggar, säkerhetsproblem, edge cases
3. Föreslå förbättringar
4. Godkänn eller begär ändringar

OUTPUT FORMAT:
## GRANSKNING

### BUGGAR HITTADE
- [Bug 1 - allvarlighetsgrad: hög/medium/låg]
- [Bug 2]

### SÄKERHETSPROBLEM
- [Problem 1]

### FÖRBÄTTRINGSFÖRSLAG
- [Förslag 1]

### VERDICT
[APPROVED ✓] eller [NEEDS CHANGES ✗]

[Om NEEDS CHANGES: lista exakt vad som måste fixas]

Var kritisk men konstruktiv. Målet är produktionsklar kod."""


# =============================================================================
# CASCADE ORCHESTRATOR
# =============================================================================

class CascadeOrchestrator:
    """
    Orkestrerar multi-agent cascade: Planner → Coder → Reviewer

    Hanterar:
    - Sekventiell körning av agenter
    - Hot-swap av modeller (VRAM-effektivt)
    - Streaming av output från varje fas
    - Sammanslagning av resultat
    """

    # Agent-konfiguration för varje roll
    # PLANNER: PHI4-reasoning 14B - chain-of-thought planering
    # CODER/REVIEWER: GPT-OSS 20B - generalist för kodning och granskning
    AGENT_ROLES = {
        CascadePhase.PLANNING: {
            "profile": "planner",  # PHI4-reasoning 14B
            "system_prompt": PLANNER_SYSTEM_PROMPT,
            "temperature": 0.3,  # Låg temp för precision i planering
        },
        CascadePhase.CODING: {
            "profile": "generalist",  # GPT-OSS 20B
            "system_prompt": CODER_SYSTEM_PROMPT,
            "temperature": 0.5,  # Balanserad för kod
        },
        CascadePhase.REVIEWING: {
            "profile": "generalist",  # GPT-OSS 20B
            "system_prompt": REVIEWER_SYSTEM_PROMPT,
            "temperature": 0.7,  # Högre för kreativ granskning
        },
    }

    def __init__(self):
        self._ollama = ollama_client
        self._orchestrator = orchestrator

    async def execute_cascade(
        self,
        task: str,
        request_id: str,
        skip_review: bool = False,
    ) -> AsyncGenerator[CascadeResult, None]:
        """
        Kör full cascade pipeline: Planner → Coder → Reviewer

        Args:
            task: Uppgiftsbeskrivning från användaren
            request_id: Unik request ID
            skip_review: Hoppa över review-fasen (snabbare)

        Yields:
            CascadeResult för varje fas med streaming content
        """
        logger.info(f"[{request_id}] Starting cascade for task: {task[:100]}...")

        # === FAS 1: PLANNING ===
        logger.info(f"[{request_id}] Phase 1: PLANNING")
        plan_content = ""

        async for result in self._run_phase(
            phase=CascadePhase.PLANNING,
            input_content=task,
            request_id=f"{request_id}-plan"
        ):
            if result.content:
                plan_content += result.content
            yield result

        if not plan_content:
            logger.error(f"[{request_id}] Planning phase produced no output")
            return

        # === FAS 2: CODING ===
        logger.info(f"[{request_id}] Phase 2: CODING")
        code_content = ""

        # Bygg context för coder
        coder_input = f"""UPPGIFT:
{task}

PLAN FRÅN PLANNER:
{plan_content}

Implementera nu koden enligt planen ovan."""

        async for result in self._run_phase(
            phase=CascadePhase.CODING,
            input_content=coder_input,
            request_id=f"{request_id}-code"
        ):
            if result.content:
                code_content += result.content
            yield result

        if not code_content:
            logger.error(f"[{request_id}] Coding phase produced no output")
            return

        # === FAS 3: REVIEWING (optional) ===
        if not skip_review:
            logger.info(f"[{request_id}] Phase 3: REVIEWING")

            # Bygg context för reviewer
            reviewer_input = f"""URSPRUNGLIG UPPGIFT:
{task}

PLAN:
{plan_content}

KOD ATT GRANSKA:
{code_content}

Granska koden ovan och ge feedback."""

            async for result in self._run_phase(
                phase=CascadePhase.REVIEWING,
                input_content=reviewer_input,
                request_id=f"{request_id}-review"
            ):
                yield result

        # === COMPLETE ===
        yield CascadeResult(
            phase=CascadePhase.COMPLETE,
            agent_id="cascade",
            content="",
            stats=None
        )
        logger.info(f"[{request_id}] Cascade complete")

    async def _run_phase(
        self,
        phase: CascadePhase,
        input_content: str,
        request_id: str,
    ) -> AsyncGenerator[CascadeResult, None]:
        """
        Kör en enskild fas i cascade-pipelinen.

        Hanterar:
        - Hot-swap av modell (unload andra)
        - Streaming av output
        - Stats collection
        """
        config = self.AGENT_ROLES[phase]
        profile = config["profile"]

        # Hot-swap: Unload andra modeller för att frigöra VRAM
        logger.info(f"[{request_id}] Hot-swap: Loading {profile}")
        try:
            unloaded = await self._ollama.unload_other_models(profile)
            if unloaded:
                logger.info(f"[{request_id}] Unloaded models: {unloaded}")
        except Exception as e:
            logger.warning(f"[{request_id}] Hot-swap warning: {e}")

        # Bygg messages med custom system prompt
        messages = [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": input_content}
        ]

        # Streama från orchestrator
        try:
            async for token, stats, agent_id in self._orchestrator.chat_stream(
                messages=messages,
                request_id=request_id,
                profile=profile,
                temperature=config["temperature"]
            ):
                if stats:
                    # Final stats
                    yield CascadeResult(
                        phase=phase,
                        agent_id=agent_id,
                        content="",
                        stats=stats
                    )
                else:
                    # Streaming token
                    yield CascadeResult(
                        phase=phase,
                        agent_id=agent_id,
                        content=token,
                        stats=None
                    )
        except Exception as e:
            logger.error(f"[{request_id}] Phase {phase.value} error: {e}")
            yield CascadeResult(
                phase=phase,
                agent_id=profile,
                content=f"\n[ERROR] {phase.value} failed: {str(e)}",
                stats=None
            )

    async def quick_cascade(
        self,
        task: str,
        request_id: str,
    ) -> Dict[str, str]:
        """
        Kör cascade och returnera sammanslaget resultat (ej streaming).

        Returns:
            {"plan": "...", "code": "...", "review": "..."}
        """
        results = {"plan": "", "code": "", "review": ""}

        async for result in self.execute_cascade(task, request_id):
            if result.phase == CascadePhase.PLANNING:
                results["plan"] += result.content
            elif result.phase == CascadePhase.CODING:
                results["code"] += result.content
            elif result.phase == CascadePhase.REVIEWING:
                results["review"] += result.content

        return results


# Global instance
cascade_orchestrator = CascadeOrchestrator()


def get_cascade_orchestrator() -> CascadeOrchestrator:
    """Dependency injection helper"""
    return cascade_orchestrator
