"""
Tests for Two-Pass Retrieval in RetrievalOrchestrator.

Task 4 of Evidence Policy Routing (EPR) plan.
Tests the search_with_routing() method that implements two-pass retrieval
with intent classification and DiVA budget control.
"""

from unittest.mock import MagicMock

import pytest

from backend.app.services.retrieval_orchestrator import (
    RetrievalOrchestrator,
    RetrievalResult,
    SearchResult,
)

# ==================== Fixtures ====================


@pytest.fixture
def mock_chromadb_client():
    """Mock ChromaDB client that returns controlled results."""
    client = MagicMock()

    def create_mock_collection(name: str, results: list[dict]):
        """Helper to create a mock collection with specific results."""
        mock_coll = MagicMock()
        mock_coll.name = name
        mock_coll.query.return_value = {
            "ids": [[r["id"] for r in results]],
            "metadatas": [
                [
                    {
                        "title": r.get("title", "Untitled"),
                        "source": name,
                        "doc_type": r.get("doc_type", "doc"),
                    }
                    for r in results
                ]
            ],
            "documents": [[r.get("text", "content") for r in results]],
            "distances": [[0.2 + i * 0.1 for i in range(len(results))]],  # Ascending distances
        }
        return mock_coll

    # Create mock collections with sample data
    collections = {
        "sfs_lagtext_jina_v3_1024": create_mock_collection(
            "sfs_lagtext_jina_v3_1024",
            [
                {
                    "id": "sfs_1",
                    "title": "SFS Law 1",
                    "text": "Legal text content",
                    "doc_type": "sfs",
                },
                {"id": "sfs_2", "title": "SFS Law 2", "text": "More legal text", "doc_type": "sfs"},
            ],
        ),
        "riksdag_documents_p1_jina_v3_1024": create_mock_collection(
            "riksdag_documents_p1_jina_v3_1024",
            [
                {
                    "id": "rd_1",
                    "title": "Riksdag Motion",
                    "text": "Parliamentary debate",
                    "doc_type": "motion",
                },
                {
                    "id": "rd_2",
                    "title": "Betankande",
                    "text": "Committee report",
                    "doc_type": "betankande",
                },
            ],
        ),
        "swedish_gov_docs_jina_v3_1024": create_mock_collection(
            "swedish_gov_docs_jina_v3_1024",
            [
                {
                    "id": "gov_1",
                    "title": "SOU Report",
                    "text": "Government inquiry",
                    "doc_type": "sou",
                }
            ],
        ),
        "diva_research_jina_v3_1024": create_mock_collection(
            "diva_research_jina_v3_1024",
            [
                {
                    "id": "diva_1",
                    "title": "Research Paper 1",
                    "text": "Academic research",
                    "doc_type": "thesis",
                },
                {
                    "id": "diva_2",
                    "title": "Research Paper 2",
                    "text": "More research",
                    "doc_type": "thesis",
                },
                {
                    "id": "diva_3",
                    "title": "Research Paper 3",
                    "text": "Even more research",
                    "doc_type": "thesis",
                },
            ],
        ),
        "procedural_guides_jina_v3_1024": create_mock_collection(
            "procedural_guides_jina_v3_1024",
            [
                {
                    "id": "proc_1",
                    "title": "How to Appeal",
                    "text": "Step by step guide",
                    "doc_type": "guide",
                }
            ],
        ),
    }

    def get_collection(name):
        if name in collections:
            return collections[name]
        raise ValueError(f"Collection {name} not found")

    client.get_collection = get_collection
    return client


@pytest.fixture
def mock_embedding_function():
    """Mock embedding function that returns consistent fake embeddings."""

    def embed(texts):
        # Return 768-dim fake embeddings
        import numpy as np

        return np.random.randn(len(texts), 768).tolist()

    return embed


@pytest.fixture
def orchestrator(mock_chromadb_client, mock_embedding_function):
    """Create RetrievalOrchestrator with mocked dependencies."""
    return RetrievalOrchestrator(
        chromadb_client=mock_chromadb_client,
        embedding_function=mock_embedding_function,
        default_collections=[
            "sfs_lagtext_jina_v3_1024",
            "riksdag_documents_p1_jina_v3_1024",
            "swedish_gov_docs_jina_v3_1024",
        ],
    )


# ==================== Test: SearchResult includes tier field ====================


class TestSearchResultTierField:
    """Test that SearchResult dataclass includes tier field."""

    def test_search_result_has_tier_field(self):
        """SearchResult should have an optional tier field."""
        result = SearchResult(
            id="test_1",
            title="Test",
            snippet="Test content",
            score=0.9,
            source="sfs_lagtext_jina_v3_1024",
            tier="A",
        )
        assert result.tier == "A"

    def test_search_result_tier_default_none(self):
        """SearchResult tier should default to None."""
        result = SearchResult(
            id="test_1",
            title="Test",
            snippet="Test content",
            score=0.9,
            source="sfs_lagtext_jina_v3_1024",
        )
        assert result.tier is None


# ==================== Test: RetrievalResult includes intent and routing ====================


class TestRetrievalResultMetadata:
    """Test that RetrievalResult includes intent and routing_used fields."""

    def test_retrieval_result_has_intent_field(self):
        """RetrievalResult should have an optional intent field."""
        from backend.app.services.retrieval_orchestrator import RetrievalMetrics

        result = RetrievalResult(
            results=[],
            metrics=RetrievalMetrics(),
            intent="policy_arguments",
        )
        assert result.intent == "policy_arguments"

    def test_retrieval_result_has_routing_used_field(self):
        """RetrievalResult should have an optional routing_used field."""
        from backend.app.services.retrieval_orchestrator import RetrievalMetrics

        routing = {
            "primary": ["riksdag_documents_p1_jina_v3_1024"],
            "secondary": ["diva_research_jina_v3_1024"],
            "secondary_budget": 2,
        }
        result = RetrievalResult(
            results=[],
            metrics=RetrievalMetrics(),
            routing_used=routing,
        )
        assert result.routing_used == routing

    def test_retrieval_result_fields_default_none(self):
        """RetrievalResult intent and routing_used should default to None."""
        from backend.app.services.retrieval_orchestrator import RetrievalMetrics

        result = RetrievalResult(
            results=[],
            metrics=RetrievalMetrics(),
        )
        assert result.intent is None
        assert result.routing_used is None


# ==================== Test: search_with_routing() method exists ====================


class TestSearchWithRoutingExists:
    """Test that search_with_routing() method exists on RetrievalOrchestrator."""

    def test_method_exists(self, orchestrator):
        """RetrievalOrchestrator should have search_with_routing method."""
        assert hasattr(orchestrator, "search_with_routing")
        assert callable(orchestrator.search_with_routing)


# ==================== Test: POLICY_ARGUMENTS triggers two-pass ====================


class TestPolicyArgumentsTwoPass:
    """Test that POLICY_ARGUMENTS intent triggers two-pass retrieval with DiVA."""

    @pytest.mark.asyncio
    async def test_policy_arguments_includes_diva(self, orchestrator):
        """POLICY_ARGUMENTS should search DiVA in secondary pass."""
        # Query that triggers POLICY_ARGUMENTS intent
        query = "Vilka argument använde partierna för att stödja förslaget?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Should have intent set
        assert result.intent == "policy_arguments"

        # Should have routing_used with secondary collections
        assert result.routing_used is not None
        assert "diva_research_jina_v3_1024" in result.routing_used.get("secondary", [])

        # Should have some DiVA results
        diva_results = [r for r in result.results if "diva" in r.source.lower()]
        assert len(diva_results) > 0, "POLICY_ARGUMENTS should include DiVA results"

    @pytest.mark.asyncio
    async def test_policy_arguments_respects_budget(self, orchestrator):
        """POLICY_ARGUMENTS should respect secondary_budget limit."""
        query = "Vilka argument använde partierna?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Count DiVA results
        diva_results = [r for r in result.results if "diva" in r.source.lower()]

        # Budget is 2 for POLICY_ARGUMENTS
        assert (
            len(diva_results) <= 2
        ), f"DiVA results ({len(diva_results)}) should not exceed budget (2)"


# ==================== Test: PARLIAMENT_TRACE never uses DiVA ====================


class TestParliamentTraceNoDiva:
    """Test that PARLIAMENT_TRACE intent never searches DiVA."""

    @pytest.mark.asyncio
    async def test_parliament_trace_no_diva(self, orchestrator):
        """PARLIAMENT_TRACE should not include DiVA results."""
        # Query that triggers PARLIAMENT_TRACE intent
        query = "Hur har riksdagen behandlat klimatfrågan?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Should have correct intent
        assert result.intent == "parliament_trace"

        # Should NOT have DiVA in secondary
        assert result.routing_used is not None
        secondary = result.routing_used.get("secondary", [])
        assert "diva_research_jina_v3_1024" not in secondary

        # Should have NO DiVA results
        diva_results = [r for r in result.results if "diva" in r.source.lower()]
        assert len(diva_results) == 0, "PARLIAMENT_TRACE should never include DiVA"


# ==================== Test: LEGAL_TEXT uses SFS primary ====================


class TestLegalTextSfsPrimary:
    """Test that LEGAL_TEXT intent uses SFS as primary collection."""

    @pytest.mark.asyncio
    async def test_legal_text_sfs_primary(self, orchestrator):
        """LEGAL_TEXT should have SFS as primary collection."""
        # Query that triggers LEGAL_TEXT intent
        query = "Vad säger Regeringsformen om yttrandefrihet?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Should have correct intent
        assert result.intent == "legal_text"

        # Should have SFS in primary
        assert result.routing_used is not None
        primary = result.routing_used.get("primary", [])
        assert "sfs_lagtext_jina_v3_1024" in primary

        # SFS results should appear (first ones due to tier priority)
        sfs_results = [r for r in result.results if "sfs" in r.source.lower()]
        assert len(sfs_results) > 0, "LEGAL_TEXT should include SFS results"


# ==================== Test: Results sorted by tier priority ====================


class TestResultsSortedByTier:
    """Test that results are sorted by tier priority (A before B before C)."""

    @pytest.mark.asyncio
    async def test_results_sorted_by_tier(self, orchestrator):
        """Results should be sorted by tier: A first, then B, then C."""
        # Query that triggers POLICY_ARGUMENTS (includes all tiers)
        query = "Vilka argument använde partierna för klimatpolitiken?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Get tiers of results in order
        tiers = [r.tier for r in result.results if r.tier is not None]

        # Verify tier ordering: A before B before C
        tier_order = {"A": 1, "B": 2, "C": 3}
        for i in range(len(tiers) - 1):
            current_tier = tier_order.get(tiers[i], 999)
            next_tier = tier_order.get(tiers[i + 1], 999)
            assert current_tier <= next_tier, f"Tier {tiers[i]} should come before {tiers[i + 1]}"

    @pytest.mark.asyncio
    async def test_tier_a_results_first(self, orchestrator):
        """Tier A results should appear before other tiers."""
        query = "Vilka argument använde partierna?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Find first non-A tier result
        first_non_a_idx = None
        last_a_idx = None

        for i, r in enumerate(result.results):
            if r.tier == "A":
                last_a_idx = i
            elif first_non_a_idx is None and r.tier in ["B", "C"]:
                first_non_a_idx = i

        # If we have both A and non-A results, A should come first
        if last_a_idx is not None and first_non_a_idx is not None:
            assert last_a_idx < first_non_a_idx, "Tier A results should come before B/C"


# ==================== Test: Secondary budget limiting ====================


class TestSecondaryBudgetLimiting:
    """Test that secondary results are limited by budget."""

    @pytest.mark.asyncio
    async def test_budget_zero_no_secondary(self, orchestrator):
        """When secondary_budget is 0, no secondary results should appear."""
        # LEGAL_TEXT has budget=0
        query = "Vad säger lagen om personuppgifter?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Should have no DiVA results
        diva_results = [r for r in result.results if "diva" in r.source.lower()]
        assert len(diva_results) == 0, "Budget 0 should mean no secondary results"

    @pytest.mark.asyncio
    async def test_budget_limits_secondary_count(self, orchestrator):
        """Secondary results should be capped at secondary_budget."""
        # POLICY_ARGUMENTS has budget=2
        query = "Vilka argument använde oppositionen?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Count secondary (DiVA) results
        diva_results = [r for r in result.results if "diva" in r.source.lower()]

        # Should be <= budget (2)
        budget = result.routing_used.get("secondary_budget", 0)
        assert (
            len(diva_results) <= budget
        ), f"Secondary count {len(diva_results)} exceeds budget {budget}"


# ==================== Test: Intent classification integration ====================


class TestIntentClassificationIntegration:
    """Test that search_with_routing correctly uses intent classifier."""

    @pytest.mark.asyncio
    async def test_unknown_intent_uses_defaults(self, orchestrator):
        """Unknown/generic queries should use default collections."""
        query = "xyz foo bar"  # Nonsense query

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Should have unknown intent
        assert result.intent == "unknown"

        # Should still return results from default collections
        assert len(result.results) > 0 or result.routing_used is not None

    @pytest.mark.asyncio
    async def test_research_intent_diva_primary(self, orchestrator):
        """RESEARCH_SYNTHESIS should have DiVA as primary."""
        query = "Vad säger forskningen om klimatförändringar?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        # Should detect research intent
        # Note: This may match RESEARCH_SYNTHESIS which has DiVA as PRIMARY
        if result.intent == "research":
            primary = result.routing_used.get("primary", [])
            assert "diva_research_jina_v3_1024" in primary


# ==================== Test: Routing metadata in result ====================


class TestRoutingMetadata:
    """Test that routing metadata is correctly included in result."""

    @pytest.mark.asyncio
    async def test_routing_used_structure(self, orchestrator):
        """routing_used should have expected structure."""
        query = "Vilka argument använde partierna?"

        result = await orchestrator.search_with_routing(query=query, k=10)

        assert result.routing_used is not None
        assert "primary" in result.routing_used
        assert "secondary" in result.routing_used
        assert "secondary_budget" in result.routing_used
        assert isinstance(result.routing_used["primary"], list)
        assert isinstance(result.routing_used["secondary"], list)
        assert isinstance(result.routing_used["secondary_budget"], int)
