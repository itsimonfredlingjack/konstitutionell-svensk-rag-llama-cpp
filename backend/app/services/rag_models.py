"""
RAG Pipeline Models — Data containers for the Constitutional AI RAG system.

Extracted from orchestrator_service.py to enable clean imports without
pulling in the entire orchestrator dependency chain.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .query_processor_service import ResponseMode
from .guardrail_service import WardenStatus
from .retrieval_service import SearchResult


# ── Response Templates ──────────────────────────────────────────────


class ResponseTemplates:
    """Constants for response templates to avoid magic strings."""

    EVIDENCE_REFUSAL = (
        "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. "
        "Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera. "
        "Om du vill kan du omformulera frågan eller ange vilka dokument/avsnitt du vill att jag ska söker i."
    )

    SAFE_FALLBACK = "Jag kunde inte tolka modellens strukturerade svar. Försök igen."

    STRUCTURED_OUTPUT_RETRY_INSTRUCTION = (
        "Du returnerade ogiltig JSON. Returnera endast giltig JSON enligt schema, "
        "inga backticks, ingen extra text."
    )


# ── Answer Contracts ────────────────────────────────────────────────

from .intent_classifier import QueryIntent

ANSWER_CONTRACTS = {
    QueryIntent.PARLIAMENT_TRACE: """
## Svarsformat: Riksdagens hantering

Strukturera svaret som:
1. **Tidslinje**: motion/proposition → utskott → betänkande → votering/beslut
2. **Källcitat**: Minst 2 citat från riksdagsdokument
3. **Aktörer**: Vilka partier/utskott var involverade

ALDRIG spekulera om beslut som inte finns i källorna.
Om underlag saknas, skriv: "Underlag för denna fråga saknas i de hämtade dokumenten."
""",
    QueryIntent.POLICY_ARGUMENTS: """
## Svarsformat: Politiska argument

Strukturera svaret i TVÅ separata delar:

### Del A: Riksdagens hantering (PRIMÄRT)
- Vilka argument framfördes i riksdagen
- Källhänvisningar till propositioner/motioner/betänkanden

### Del B: Forskningsbakgrund (SEKUNDÄRT, om hämtat)
- Markera tydligt: "Forskning indikerar att..."
- BLANDA ALDRIG ihop med riksdagskällor
- Om ingen forskning hämtades, utelämna denna del

REGEL: Del A får ALDRIG bygga på Del B som källa.
""",
    QueryIntent.RESEARCH_SYNTHESIS: """
## Svarsformat: Forskningssyntes

OBS: Detta svar handlar om FORSKNING, inte riksdagsbeslut.

1. Sammanfatta forskningsläget (3-5 punkter)
2. Ange käll-ID för varje påstående
3. Avsluta med: "Detta är forskningsläget, inte riksdagens ställningstagande."

Vid medicinsk/hälsorelaterad forskning: Ge neutral information, ingen behandlingsrådgivning.
""",
    QueryIntent.LEGAL_TEXT: """
## Svarsformat: Lagtext

1. CITERA ORDAGRANT från lagtexten
2. Format: "Enligt [LAG] [kap.] [§]: '[EXAKT CITAT]'"
3. Ingen tolkning utanför lagtextens lydelse
4. Vid osäkerhet: "Lagtexten anger X, men tillämpning kräver myndighetsbedömning."
""",
    QueryIntent.PRACTICAL_PROCESS: """
## Svarsformat: Praktisk process

1. Lista stegen i numrerad ordning
2. Ange relevanta myndigheter/instanser
3. Inkludera tidsfrister om de nämns i källorna
4. Vid rättsmedel: "Överklagan ska ske till [INSTANS] inom [TID] från [HÄNDELSE]."
""",
}


def get_answer_contract(intent: QueryIntent) -> str:
    """Get the answer contract/prompt template for an intent."""
    return ANSWER_CONTRACTS.get(intent, "")


# ── Pipeline Metrics ────────────────────────────────────────────────


@dataclass
class RAGPipelineMetrics:
    """
    Metrics for the complete RAG pipeline.
    """

    # Timing
    query_classification_ms: float = 0.0
    decontextualization_ms: float = 0.0
    retrieval_ms: float = 0.0
    llm_generation_ms: float = 0.0
    guardrail_ms: float = 0.0
    reranking_ms: float = 0.0
    total_pipeline_ms: float = 0.0

    # Component results
    mode: str = "assist"
    sources_count: int = 0
    tokens_generated: int = 0
    corrections_count: int = 0

    # Retrieval details
    retrieval_strategy: str = "parallel_v1"
    retrieval_results_count: int = 0
    top_relevance_score: float = 0.0

    # Guardrail details
    guardrail_status: str = "unchanged"
    evidence_level: str = "NONE"

    # LLM details
    model_used: str = ""
    llm_latency_ms: float = 0.0
    tokens_per_second: float = 0.0

    # Structured Output details
    structured_output_ms: float = 0.0
    parse_errors: bool = False
    saknas_underlag: Optional[bool] = None
    kallor_count: int = 0
    structured_output_enabled: bool = False

    # Critic/Revise details
    critic_revision_count: int = 0
    critic_ms: float = 0.0
    critic_ok: bool = False

    # CRAG (Corrective RAG) details
    crag_enabled: bool = False
    grade_count: int = 0
    relevant_count: int = 0
    grade_ms: float = 0.0
    self_reflection_used: bool = False
    self_reflection_ms: float = 0.0
    rewrite_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "pipeline": {
                "classification_ms": round(self.query_classification_ms, 2),
                "decontextualization_ms": round(self.decontextualization_ms, 2),
                "retrieval_ms": round(self.retrieval_ms, 2),
                "llm_generation_ms": round(self.llm_generation_ms, 2),
                "guardrail_ms": round(self.guardrail_ms, 2),
                "reranking_ms": round(self.reranking_ms, 2),
                "total_ms": round(self.total_pipeline_ms, 2),
            },
            "retrieval": {
                "strategy": self.retrieval_strategy,
                "results_count": self.retrieval_results_count,
                "top_relevance_score": round(self.top_relevance_score, 4),
            },
            "guardrail": {
                "status": self.guardrail_status,
                "evidence_level": self.evidence_level,
                "corrections_count": self.corrections_count,
            },
            "llm": {
                "model": self.model_used,
                "latency_ms": round(self.llm_latency_ms, 2),
                "tokens_per_second": round(self.tokens_per_second, 2),
            },
        }


# ── Citation ────────────────────────────────────────────────────────


@dataclass
class Citation:
    """A citation linking a claim to its source."""

    claim: str
    source_id: str
    source_title: str
    source_collection: str
    tier: str


# ── RAG Result ──────────────────────────────────────────────────────


@dataclass
class RAGResult:
    """
    Complete result from RAG pipeline.

    Contains the final answer, sources, and full metrics.
    """

    answer: str
    sources: List[SearchResult]
    reasoning_steps: List[str]
    metrics: RAGPipelineMetrics
    mode: ResponseMode
    guardrail_status: WardenStatus
    evidence_level: str
    success: bool = True
    error: Optional[str] = None
    thought_chain: Optional[str] = None
    citations: List[Citation] = field(default_factory=list)
    intent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        result = {
            "answer": self.answer,
            "sources": [
                {
                    "id": s.id,
                    "title": s.title,
                    "snippet": s.snippet,
                    "score": s.score,
                    "source": s.source,
                    "doc_type": s.doc_type,
                    "date": s.date,
                }
                for s in self.sources
            ],
            "reasoning_steps": self.reasoning_steps,
            "metrics": self.metrics.to_dict(),
            "mode": self.mode.value,
            "guardrail_status": self.guardrail_status.value,
            "evidence_level": self.evidence_level,
            "success": self.success,
            "error": self.error,
        }

        if self.thought_chain and self.mode.value in ["assist", "evidence"]:
            result["thought_chain"] = self.thought_chain

        return result
