"""
Test suite for Citations as first-class API response field.

Tests:
- Citation dataclass structure and fields
- CitationItem Pydantic model validation
- AgentQueryResponse with citations field
- Default empty list behavior
"""


class TestCitationDataclass:
    """Test Citation dataclass in orchestrator_service.py"""

    def test_citation_has_required_fields(self):
        """Citation dataclass must have all required fields."""
        from backend.app.services.rag_models import Citation

        # Create a Citation instance
        citation = Citation(
            claim="Skatteverket har rätt att begära dokumentation",
            source_id="doc-123",
            source_title="Skatteförfarandelagen 2011:1244",
            source_collection="lagar",
            tier="A",
        )

        assert citation.claim == "Skatteverket har rätt att begära dokumentation"
        assert citation.source_id == "doc-123"
        assert citation.source_title == "Skatteförfarandelagen 2011:1244"
        assert citation.source_collection == "lagar"
        assert citation.tier == "A"

    def test_citation_is_dataclass(self):
        """Citation should be a proper dataclass."""
        from dataclasses import is_dataclass

        from backend.app.services.rag_models import Citation

        assert is_dataclass(Citation), "Citation must be a dataclass"

    def test_citation_fields_are_strings(self):
        """All Citation fields should be strings."""
        from dataclasses import fields

        from backend.app.services.rag_models import Citation

        citation_fields = {f.name: f.type for f in fields(Citation)}

        assert citation_fields["claim"] is str
        assert citation_fields["source_id"] is str
        assert citation_fields["source_title"] is str
        assert citation_fields["source_collection"] is str
        assert citation_fields["tier"] is str


class TestRAGResultCitations:
    """Test RAGResult dataclass has citations field."""

    def test_ragresult_has_citations_field(self):
        """RAGResult must have a citations field."""
        from dataclasses import fields

        from backend.app.services.orchestrator_service import RAGResult

        field_names = [f.name for f in fields(RAGResult)]
        assert "citations" in field_names, "RAGResult must have citations field"

    def test_ragresult_citations_defaults_to_empty_list(self):
        """RAGResult.citations should default to empty list."""
        from backend.app.services.guardrail_service import WardenStatus
        from backend.app.services.orchestrator_service import (
            RAGPipelineMetrics,
            RAGResult,
        )
        from backend.app.services.query_processor_service import ResponseMode

        result = RAGResult(
            answer="Test answer",
            sources=[],
            reasoning_steps=[],
            metrics=RAGPipelineMetrics(),
            mode=ResponseMode.ASSIST,
            guardrail_status=WardenStatus.UNCHANGED,
            evidence_level="NONE",
        )

        assert result.citations == []
        assert isinstance(result.citations, list)

    def test_ragresult_has_intent_field(self):
        """RAGResult must have an intent field for EPR."""
        from dataclasses import fields

        from backend.app.services.orchestrator_service import RAGResult

        field_names = [f.name for f in fields(RAGResult)]
        assert "intent" in field_names, "RAGResult must have intent field"


class TestCitationItemModel:
    """Test CitationItem Pydantic model in constitutional_routes.py"""

    def test_citationitem_model_exists(self):
        """CitationItem model must exist."""
        from backend.app.api.constitutional_routes import CitationItem

        assert CitationItem is not None

    def test_citationitem_has_required_fields(self):
        """CitationItem must have all required fields."""
        from backend.app.api.constitutional_routes import CitationItem

        item = CitationItem(
            claim="Test claim",
            source_id="src-1",
            source_title="Test Title",
            source_collection="test_collection",
            tier="B",
        )

        assert item.claim == "Test claim"
        assert item.source_id == "src-1"
        assert item.source_title == "Test Title"
        assert item.source_collection == "test_collection"
        assert item.tier == "B"

    def test_citationitem_validation(self):
        """CitationItem should validate string fields."""

        from backend.app.api.constitutional_routes import CitationItem

        # Should work with valid strings
        item = CitationItem(
            claim="Valid claim",
            source_id="id",
            source_title="title",
            source_collection="collection",
            tier="A",
        )
        assert item.claim == "Valid claim"

    def test_citationitem_is_pydantic_model(self):
        """CitationItem should be a Pydantic BaseModel."""
        from pydantic import BaseModel

        from backend.app.api.constitutional_routes import CitationItem

        assert issubclass(CitationItem, BaseModel)


class TestAgentQueryResponseCitations:
    """Test AgentQueryResponse has citations field."""

    def test_agentqueryresponse_has_citations_field(self):
        """AgentQueryResponse must have a citations field."""
        from backend.app.api.constitutional_routes import AgentQueryResponse

        # Check field exists in model
        assert "citations" in AgentQueryResponse.model_fields

    def test_agentqueryresponse_citations_defaults_to_empty_list(self):
        """AgentQueryResponse.citations should default to empty list."""
        from backend.app.api.constitutional_routes import AgentQueryResponse

        response = AgentQueryResponse(
            answer="Test answer",
            sources=[],
            mode="assist",
            saknas_underlag=False,
        )

        assert response.citations == []
        assert isinstance(response.citations, list)

    def test_agentqueryresponse_has_intent_field(self):
        """AgentQueryResponse must have an intent field for EPR."""
        from backend.app.api.constitutional_routes import AgentQueryResponse

        assert "intent" in AgentQueryResponse.model_fields

    def test_agentqueryresponse_intent_defaults_to_none(self):
        """AgentQueryResponse.intent should default to None."""
        from backend.app.api.constitutional_routes import AgentQueryResponse

        response = AgentQueryResponse(
            answer="Test answer",
            sources=[],
            mode="assist",
            saknas_underlag=False,
        )

        assert response.intent is None

    def test_agentqueryresponse_with_citations(self):
        """AgentQueryResponse should accept CitationItem list."""
        from backend.app.api.constitutional_routes import (
            AgentQueryResponse,
            CitationItem,
        )

        citations = [
            CitationItem(
                claim="First claim",
                source_id="src-1",
                source_title="Source 1",
                source_collection="collection_a",
                tier="A",
            ),
            CitationItem(
                claim="Second claim",
                source_id="src-2",
                source_title="Source 2",
                source_collection="collection_b",
                tier="B",
            ),
        ]

        response = AgentQueryResponse(
            answer="Answer with citations",
            sources=[],
            mode="evidence",
            saknas_underlag=False,
            citations=citations,
            intent="factual_query",
        )

        assert len(response.citations) == 2
        assert response.citations[0].claim == "First claim"
        assert response.citations[1].tier == "B"
        assert response.intent == "factual_query"
