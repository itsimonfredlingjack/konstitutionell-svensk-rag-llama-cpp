# tests/test_source_hierarchy.py
from backend.app.services.source_hierarchy import (
    COLLECTION_TIERS,
    SourceHierarchy,
    SourceTier,
)


def test_collection_tier_assignment():
    """Each collection maps to correct tier."""
    assert COLLECTION_TIERS["sfs_lagtext_jina_v3_1024"] == SourceTier.A
    assert COLLECTION_TIERS["riksdag_documents_p1_jina_v3_1024"] == SourceTier.A
    assert COLLECTION_TIERS["swedish_gov_docs_jina_v3_1024"] == SourceTier.B
    assert COLLECTION_TIERS["procedural_guides_jina_v3_1024"] == SourceTier.B
    assert COLLECTION_TIERS["diva_research_jina_v3_1024"] == SourceTier.C


def test_tier_priority_ordering():
    """Tier A > B > C in priority."""
    assert SourceTier.A.value < SourceTier.B.value < SourceTier.C.value


def test_get_tier_for_unknown_collection():
    """Unknown collections default to lowest tier."""
    hierarchy = SourceHierarchy()
    assert hierarchy.get_tier("unknown_collection") == SourceTier.C


def test_sort_by_priority():
    """sort_by_priority orders results by tier (A first)."""
    hierarchy = SourceHierarchy()
    results = [
        {"source": "diva_research_jina_v3_1024", "text": "C tier"},
        {"source": "sfs_lagtext_jina_v3_1024", "text": "A tier"},
        {"source": "swedish_gov_docs_jina_v3_1024", "text": "B tier"},
    ]
    sorted_results = hierarchy.sort_by_priority(results)
    assert sorted_results[0]["source"] == "sfs_lagtext_jina_v3_1024"
    assert sorted_results[1]["source"] == "swedish_gov_docs_jina_v3_1024"
    assert sorted_results[2]["source"] == "diva_research_jina_v3_1024"
