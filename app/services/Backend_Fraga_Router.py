"""
Multi-Agent Orchestrator - Routes requests to AI agents

AGENTS:
- PLANNER: PHI4-reasoning 14B - Planering
- GENERALIST: GPT-OSS 20B - Generalist

SYSTEM prompts finns i Modelfiles - backend skickar BARA user messages.
"""

import re
from enum import Enum
from typing import AsyncGenerator, Optional, Dict, Any
from dataclasses import dataclass

from .ollama_client import ollama_client, OllamaClient, StreamStats, OllamaError
from .intelligence import intelligence, OutputFormat
from ..utils.logging import get_logger
from ..config import (
    MODEL_PLANNER, MODEL_PLANNER_NAME,
    MODEL_GENERALIST, MODEL_GENERALIST_NAME,
)

logger = get_logger(__name__)


# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

class AgentId(str, Enum):
    """Agent identifiers matching frontend expectations"""
    PLANNER = "planner"       # PHI4-reasoning 14B
    GENERALIST = "generalist" # GPT-OSS 20B


class Provider(str, Enum):
    """Backend providers"""
    OLLAMA = "ollama"


@dataclass
class AgentConfig:
    """Configuration for an AI agent (NO system_prompt - that's in Modelfile)"""
    id: AgentId
    display_name: str
    provider: Provider
    model: str
    temperature: float = 0.7
    description: str = ""


# =============================================================================
# AGENT CONFIGURATIONS (prompts in Modelfiles)
# =============================================================================

AGENTS: Dict[AgentId, AgentConfig] = {
    AgentId.PLANNER: AgentConfig(
        id=AgentId.PLANNER,
        display_name=MODEL_PLANNER_NAME,
        provider=Provider.OLLAMA,
        model=MODEL_PLANNER,
        temperature=0.3,
        description="Planering (PHI4-reasoning 14B)"
    ),
    AgentId.GENERALIST: AgentConfig(
        id=AgentId.GENERALIST,
        display_name=MODEL_GENERALIST_NAME,
        provider=Provider.OLLAMA,
        model=MODEL_GENERALIST,
        temperature=0.7,
        description="Generalist (GPT-OSS 20B)"
    ),
}


def get_agent(agent_id: str) -> AgentConfig:
    """Get agent config by ID, defaults to GENERALIST"""
    try:
        normalized = agent_id.lower().replace("_", "-")
        return AGENTS[AgentId(normalized)]
    except (ValueError, KeyError):
        logger.warning(f"Unknown agent '{agent_id}', defaulting to GENERALIST")
        return AGENTS[AgentId.GENERALIST]


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
    agent_id: str = "generalist"

    @classmethod
    def from_ollama(cls, stats: StreamStats, model: str, agent_id: str = "generalist") -> "UnifiedStats":
        return cls(
            tokens_generated=stats.tokens_generated,
            tokens_per_second=stats.tokens_per_second,
            total_duration_ms=stats.total_duration_ms,
            prompt_tokens=stats.prompt_eval_count,
            provider="ollama",
            model=model,
            agent_id=agent_id
        )



# =============================================================================
# ORCHESTRATOR
# =============================================================================

class MultiAgentOrchestrator:
    """
    Routes requests to the appropriate AI agent.
    System prompts are in Modelfiles - we just forward messages.
    """

    def __init__(self):
        self._ollama = ollama_client
        self._ollama_clients = {
            "planner": ollama_client,
            "generalist": ollama_client,
        }

    async def chat_stream(
        self,
        messages: list[dict],
        request_id: str,
        profile: str = "generalist",
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[tuple[str, Optional[UnifiedStats], str], None]:
        """
        Stream chat completion to the specified agent.
        NO system prompt injection - Modelfile has the prompt.
        """
        agent = get_agent(profile)
        temp = temperature if temperature is not None else agent.temperature

        logger.info(
            f"[{request_id}] Routing to agent: {agent.display_name} "
            f"(model={agent.model}, provider={agent.provider.value})"
        )

        try:
            # OLLAMA (local models only)
            # NO system prompt injection - Modelfile has it
            msgs_clean = [
                {"role": m.get("role"), "content": m.get("content")}
                for m in messages if m.get("role") != "system"
            ]

            class SimpleProfile:
                def __init__(self, agent_id: str, model: str, temp: float, max_tok: int):
                    self.id = agent_id
                    self.model = model
                    self.temperature = temp
                    self.top_p = 0.9
                    self.repeat_penalty = 1.1
                    self.max_tokens = max_tok
                    self.context_length = 4096

            profile_obj = SimpleProfile(agent.id.value, agent.model, temp, max_tokens)
            agent_ollama = self._ollama_clients.get(agent.id.value, self._ollama)

            async for token, stats in agent_ollama.chat_stream(
                profile=profile_obj,
                messages=msgs_clean,
                request_id=request_id
            ):
                if stats:
                    yield "", UnifiedStats.from_ollama(stats, agent.model, agent.id.value), agent.id.value
                else:
                    yield token, None, agent.id.value

        except OllamaError as e:
            logger.error(f"[{request_id}] Agent {agent.id.value} failed: {e}")
            raise

    async def get_status(self) -> dict:
        """Get status of all agents"""
        ollama_ok = await self._ollama.is_connected()

        return {
            "agents": {
                "planner": {
                    "available": ollama_ok,
                    "model": MODEL_PLANNER,
                    "display_name": MODEL_PLANNER_NAME,
                    "provider": "ollama",
                    "server": "localhost:11434",
                    "description": "Planering (PHI4-reasoning 14B)"
                },
                "generalist": {
                    "available": ollama_ok,
                    "model": MODEL_GENERALIST,
                    "display_name": MODEL_GENERALIST_NAME,
                    "provider": "ollama",
                    "server": "localhost:11434",
                    "description": "Generalist (GPT-OSS 20B)"
                }
            },
            "providers": {
                "ollama": {"connected": ollama_ok, "server": "localhost:11434"},
            }
        }


# Global orchestrator instance
orchestrator = MultiAgentOrchestrator()


async def get_orchestrator() -> MultiAgentOrchestrator:
    """Dependency injection helper"""
    return orchestrator
