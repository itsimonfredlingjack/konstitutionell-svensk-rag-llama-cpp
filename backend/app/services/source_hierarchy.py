"""
Source Hierarchy for Constitutional-AI RAG.
Defines normative ordering of sources for evidence-based retrieval.
"""

from enum import IntEnum
from typing import Dict, List


class SourceTier(IntEnum):
    """Source tiers in normative order. Lower value = higher priority."""

    A = 1  # Normative: SFS lagtext, Riksdag decisions
    B = 2  # Political signal: Motions, government docs
    C = 3  # Context: Academic research (DiVA)


COLLECTION_TIERS: Dict[str, SourceTier] = {
    # Tier A - Normative/Primary
    "sfs_lagtext_jina_v3_1024": SourceTier.A,
    "riksdag_documents_p1_jina_v3_1024": SourceTier.A,
    # Tier B - Political Signal
    "swedish_gov_docs_jina_v3_1024": SourceTier.B,
    "procedural_guides_jina_v3_1024": SourceTier.B,
    # Tier C - Context/Research
    "diva_research_jina_v3_1024": SourceTier.C,
}


class SourceHierarchy:
    """Manages source tier lookups and priority ordering."""

    def get_tier(self, collection_name: str) -> SourceTier:
        """Get tier for collection, default to C if unknown."""
        return COLLECTION_TIERS.get(collection_name, SourceTier.C)

    def sort_by_priority(self, results: List[dict]) -> List[dict]:
        """Sort results by source tier (A first, then B, then C)."""
        return sorted(results, key=lambda r: self.get_tier(r.get("source", "")).value)
