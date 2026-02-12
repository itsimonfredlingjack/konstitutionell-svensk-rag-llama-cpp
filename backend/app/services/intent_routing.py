"""
Intent Routing Configuration for Constitutional-AI RAG.

Defines two-pass retrieval with primary/secondary collections and DiVA budget.
Part of Evidence Policy Routing (EPR) implementation.

Collection Tiers:
- Tier A+B (primary): Official legal documents, riksdag docs, gov docs
- Tier C (secondary): DiVA research papers (requires explicit budget)
"""

from dataclasses import dataclass, field
from typing import List

from .intent_classifier import QueryIntent


@dataclass
class IntentRoutingConfig:
    """
    Configuration for routing queries based on intent.

    Attributes:
        primary: Tier A+B collections for Pass 1 retrieval
        support: Supporting collections (lower priority in ranking)
        secondary: Tier C (DiVA) collections for Pass 2 retrieval
        secondary_budget: Maximum chunks allowed from secondary collections
        require_separation: Whether to separate primary vs secondary in output
    """

    primary: List[str]
    support: List[str] = field(default_factory=list)
    secondary: List[str] = field(default_factory=list)
    secondary_budget: int = 0
    require_separation: bool = False


# ==================== Intent Routing Definitions ====================

INTENT_ROUTING = {
    QueryIntent.LEGAL_TEXT: IntentRoutingConfig(
        primary=["sfs_lagtext_jina_v3_1024"],
        support=["riksdag_documents_p1_jina_v3_1024"],
        secondary=[],
        secondary_budget=0,
    ),
    QueryIntent.PARLIAMENT_TRACE: IntentRoutingConfig(
        primary=["riksdag_documents_p1_jina_v3_1024", "swedish_gov_docs_jina_v3_1024"],
        support=["sfs_lagtext_jina_v3_1024"],
        secondary=["diva_research_jina_v3_1024"],
        secondary_budget=2,
    ),
    QueryIntent.POLICY_ARGUMENTS: IntentRoutingConfig(
        primary=["riksdag_documents_p1_jina_v3_1024", "swedish_gov_docs_jina_v3_1024"],
        support=["sfs_lagtext_jina_v3_1024"],
        secondary=["diva_research_jina_v3_1024"],
        secondary_budget=2,
        require_separation=True,
    ),
    QueryIntent.RESEARCH_SYNTHESIS: IntentRoutingConfig(
        primary=["diva_research_jina_v3_1024"],
        support=["riksdag_documents_p1_jina_v3_1024"],
        secondary=[],
        secondary_budget=0,
    ),
    QueryIntent.PRACTICAL_PROCESS: IntentRoutingConfig(
        primary=["procedural_guides_jina_v3_1024", "sfs_lagtext_jina_v3_1024"],
        support=["swedish_gov_docs_jina_v3_1024"],
        secondary=[],
        secondary_budget=0,
    ),
    QueryIntent.UNKNOWN: IntentRoutingConfig(
        primary=[
            "sfs_lagtext_jina_v3_1024",
            "riksdag_documents_p1_jina_v3_1024",
            "swedish_gov_docs_jina_v3_1024",
        ],
        support=[],
        secondary=["diva_research_jina_v3_1024"],
        secondary_budget=2,
    ),
    # EDGE cases - same routing as LEGAL_TEXT
    QueryIntent.EDGE_ABBREVIATION: IntentRoutingConfig(
        primary=["sfs_lagtext_jina_v3_1024"],
        support=["riksdag_documents_p1_jina_v3_1024"],
        secondary=[],
        secondary_budget=0,
    ),
    QueryIntent.EDGE_CLARIFICATION: IntentRoutingConfig(
        primary=["sfs_lagtext_jina_v3_1024"],
        support=["riksdag_documents_p1_jina_v3_1024"],
        secondary=[],
        secondary_budget=0,
    ),
    # SMALLTALK - empty primary (no retrieval needed)
    QueryIntent.SMALLTALK: IntentRoutingConfig(
        primary=[],
        support=[],
        secondary=[],
        secondary_budget=0,
    ),
}


def get_routing_for_intent(intent: QueryIntent) -> IntentRoutingConfig:
    """
    Get routing configuration for a given query intent.

    Args:
        intent: The classified query intent

    Returns:
        IntentRoutingConfig with collection routing and budget settings

    Raises:
        KeyError: If intent is not found in routing table (should not happen)
    """
    if intent in INTENT_ROUTING:
        return INTENT_ROUTING[intent]

    # Fallback to UNKNOWN if somehow an unrecognized intent is passed
    return INTENT_ROUTING[QueryIntent.UNKNOWN]


# ==================== Utility Functions ====================


def get_all_collections_for_intent(intent: QueryIntent) -> List[str]:
    """
    Get all collections (primary + support + secondary) for an intent.

    Useful for queries that need to search across all relevant collections.

    Args:
        intent: The classified query intent

    Returns:
        Combined list of all collections (may have duplicates removed)
    """
    config = get_routing_for_intent(intent)
    all_collections = config.primary + config.support + config.secondary
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for col in all_collections:
        if col not in seen:
            seen.add(col)
            unique.append(col)
    return unique


def has_secondary_retrieval(intent: QueryIntent) -> bool:
    """Check if intent allows secondary (DiVA) retrieval."""
    config = get_routing_for_intent(intent)
    return config.secondary_budget > 0 and len(config.secondary) > 0


# Quick self-test
if __name__ == "__main__":
    print("Intent Routing Configuration Test")
    print("=" * 60)

    for intent in QueryIntent:
        config = get_routing_for_intent(intent)
        print(f"\n{intent.value}:")
        print(f"  Primary: {config.primary}")
        print(f"  Support: {config.support}")
        print(f"  Secondary: {config.secondary}")
        print(f"  Budget: {config.secondary_budget}")
        print(f"  Require separation: {config.require_separation}")
