"""
Tests for Critic→Revise Loop Integration
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.critic_service import CriticResult
from app.services.llm_service import StreamStats
from app.services.orchestrator_service import OrchestratorService
from app.services.query_processor_service import ResponseMode
from app.services.retrieval_service import RetrievalMetrics, RetrievalResult, SearchResult


class TestCriticReviseLoop:
    """Test cases for critic→revise loop integration"""

    def setup_method(self):
        """Setup for each test method"""
        # Mock all dependencies
        self.mock_config = Mock()
        self.mock_config.structured_output_effective_enabled = True
        self.mock_config.structured_output_enabled = True
        self.mock_config.critic_revise_effective_enabled = True  # Enable critic for tests
        self.mock_config.settings.debug = False

        # FIX: Lägg till saknade config-attribut för critic→revise loop
        self.mock_config.settings.critic_max_revisions = 2
        self.mock_config.settings.critic_revise_enabled = True
        self.mock_config.settings.evidence_refusal_template = (
            "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
        )

        self.mock_config.evidence_refusal_template = (
            "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
        )

        self.mock_llm_service = Mock()
        self.mock_query_processor = Mock()
        self.mock_guardrail = Mock()
        self.mock_retrieval = Mock()
        self.mock_reranker = Mock()
        self.mock_structured_output = Mock()
        self.mock_critic = Mock()
        self.mock_critic.critique = AsyncMock()  # FIX: Make critique async
        self.mock_critic.revise = AsyncMock()  # FIX: Make revise async

        # Create orchestrator with mocked dependencies
        self.orchestrator = OrchestratorService(
            config=self.mock_config,
            llm_service=self.mock_llm_service,
            query_processor=self.mock_query_processor,
            guardrail=self.mock_guardrail,
            retrieval=self.mock_retrieval,
            reranker=self.mock_reranker,
            structured_output=self.mock_structured_output,
            critic=self.mock_critic,
        )

    @pytest.mark.asyncio
    async def test_c1_evidence_critic_ok_directly(self):
        """C1: EVIDENCE, critic ok direkt -> 0 revisions"""
        # Setup async mocks
        self.mock_llm_service.initialize = AsyncMock()
        self.mock_query_processor.initialize = AsyncMock()
        self.mock_guardrail.initialize = AsyncMock()
        self.mock_retrieval.initialize = AsyncMock()
        self.mock_structured_output.initialize = AsyncMock()
        self.mock_critic.initialize = AsyncMock()
        self.mock_llm_service.close = AsyncMock()
        self.mock_retrieval.close = AsyncMock()
        self.mock_reranker.close = AsyncMock()
        self.mock_structured_output.close = AsyncMock()
        self.mock_critic.close = AsyncMock()
        self.mock_reranker.initialize = AsyncMock()

        await self.orchestrator.initialize()

        # Setup mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}
        self.mock_query_processor.determine_evidence_level.return_value = (
            "HIGH"  # Fix Mock comparison
        )

        # Setup mock retrieval with relevant documents
        mock_sources = [
            SearchResult(
                id="gdpr_doc_1",
                title="GDPR Article 6",
                snippet="Article 6 regulates lawful processing of personal data",
                score=0.9,
                source="europa.eu",
                doc_type="law",
                date="2018-05-25",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="adaptive", top_score=0.9),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Setup mock LLM response with structured output
        structured_response = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Baserat på GDPR Artikel 6 så regleras laglig behandling av personuppgifter...", "kallor": [{"doc_id": "gdpr_doc_1", "chunk_id": "chunk_1", "citat": "Article 6 regulates lawful processing", "loc": "section 1"}], "fakta_utan_kalla": []}'

        async def mock_stream(*args, **kwargs):
            yield structured_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=50, model_used="test-model", start_time=0.0, end_time=1.0
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Setup mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = (
            "Baserat på GDPR Artikel 6..."
        )

        # Setup mock structured output service
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Baserat på GDPR Artikel 6 så regleras laglig behandling av personuppgifter...",
            "kallor": [
                {
                    "doc_id": "gdpr_doc_1",
                    "chunk_id": "chunk_1",
                    "citat": "Article 6 regulates lawful processing",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "Baserat på GDPR Artikel 6..."
        validated_schema.kallor = [
            {
                "doc_id": "gdpr_doc_1",
                "chunk_id": "chunk_1",
                "citat": "Article 6 regulates lawful processing",
                "loc": "section 1",
            }
        ]
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Baserat på GDPR Artikel 6...",
            "kallor": [
                {
                    "doc_id": "gdpr_doc_1",
                    "chunk_id": "chunk_1",
                    "citat": "Article 6 regulates lawful processing",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        # Setup mock critic - returns OK directly (no revisions needed)
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute
        result = await self.orchestrator.process_query(
            question="Vad säger GDPR om personuppgifter?", mode="evidence", enable_reranking=False
        )

        # Assertions
        assert result.success is True
        assert result.mode == ResponseMode.EVIDENCE
        assert "GDPR" in result.answer
        assert result.metrics.structured_output_enabled is True
        assert result.metrics.critic_revision_count == 0  # C1: No revisions needed
        assert result.metrics.critic_ok
        # Verify critic was called exactly once
        self.mock_critic.critique.assert_called_once()

    @pytest.mark.asyncio
    async def test_c2_evidence_critic_false_then_fixed(self):
        """C2: EVIDENCE, critic ok=false först, revise fixar -> 1 revision"""
        # Setup async mocks
        self.mock_llm_service.initialize = AsyncMock()
        self.mock_query_processor.initialize = AsyncMock()
        self.mock_guardrail.initialize = AsyncMock()
        self.mock_retrieval.initialize = AsyncMock()
        self.mock_structured_output.initialize = AsyncMock()
        self.mock_critic.initialize = AsyncMock()
        self.mock_llm_service.close = AsyncMock()
        self.mock_retrieval.close = AsyncMock()
        self.mock_reranker.close = AsyncMock()
        self.mock_structured_output.close = AsyncMock()
        self.mock_critic.close = AsyncMock()
        self.mock_reranker.initialize = AsyncMock()

        await self.orchestrator.initialize()

        # Setup mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}

        # Setup mock retrieval with relevant documents
        mock_sources = [
            SearchResult(
                id="gdpr_doc_1",
                title="GDPR Article 6",
                snippet="Article 6 regulates lawful processing of personal data",
                score=0.9,
                source="europa.eu",
                doc_type="law",
                date="2018-05-25",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="adaptive", top_score=0.9),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Setup mock LLM response with structured output (missing required field)
        structured_response = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Baserat på GDPR Artikel 6...", "kallor": []}'  # Missing "fakta_utan_kalla"

        async def mock_stream(*args, **kwargs):
            yield structured_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=50, model_used="test-model", start_time=0.0, end_time=1.0
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Setup mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = (
            "Baserat på GDPR Artikel 6..."
        )

        # Setup mock structured output service
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Baserat på GDPR Artikel 6...",
            "kallor": [],
            # Missing "fakta_utan_kalla" field
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "Baserat på GDPR Artikel 6..."
        validated_schema.kallor = []
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Baserat på GDPR Artikel 6...",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        # Setup mock critic - returns FAIL first, then OK after revision
        self.mock_critic.critique.side_effect = [
            CriticResult(  # First critique - fails
                ok=False,
                fel=["Missing required field: fakta_utan_kalla"],
                atgard="Add missing field: fakta_utan_kalla",
                latency_ms=1.0,
            ),
            CriticResult(  # Second critique - passes after revision
                ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
            ),
        ]

        # Setup mock revise to fix the missing field
        async def mock_revise(candidate_json, critic_feedback):
            # Simple revision - add the missing field
            data = json.loads(candidate_json)
            data["fakta_utan_kalla"] = []
            return json.dumps(data, ensure_ascii=False)

        self.mock_critic.revise.side_effect = mock_revise

        # Execute
        result = await self.orchestrator.process_query(
            question="Vad säger GDPR om personuppgifter?", mode="evidence", enable_reranking=False
        )

        # Assertions
        assert result.success is True
        assert result.mode == ResponseMode.EVIDENCE
        assert "GDPR" in result.answer
        assert result.metrics.structured_output_enabled is True
        assert result.metrics.critic_revision_count == 1  # C2: 1 revision needed
        assert result.metrics.critic_ok  # Final result is OK
        # Verify critic was called twice
        assert self.mock_critic.critique.call_count == 2

    @pytest.mark.asyncio
    async def test_c3_evidence_critic_still_fails_after_2_revisions(self):
        """C3: EVIDENCE, critic ok=false även efter 2 -> refusal"""
        # Setup async mocks
        self.mock_llm_service.initialize = AsyncMock()
        self.mock_query_processor.initialize = AsyncMock()
        self.mock_guardrail.initialize = AsyncMock()
        self.mock_retrieval.initialize = AsyncMock()
        self.mock_structured_output.initialize = AsyncMock()
        self.mock_critic.initialize = AsyncMock()
        self.mock_llm_service.close = AsyncMock()
        self.mock_retrieval.close = AsyncMock()
        self.mock_reranker.close = AsyncMock()
        self.mock_structured_output.close = AsyncMock()
        self.mock_critic.close = AsyncMock()
        self.mock_reranker.initialize = AsyncMock()

        await self.orchestrator.initialize()

        # Setup mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}

        # Setup mock retrieval with relevant documents
        mock_sources = [
            SearchResult(
                id="gdpr_doc_1",
                title="GDPR Article 6",
                snippet="Article 6 regulates lawful processing of personal data",
                score=0.9,
                source="europa.eu",
                doc_type="law",
                date="2018-05-25",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="adaptive", top_score=0.9),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Setup mock LLM response with structured output
        structured_response = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Baserat på GDPR Artikel 6...", "kallor": []}'  # Invalid - missing required fields

        async def mock_stream(*args, **kwargs):
            yield structured_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=50, model_used="test-model", start_time=0.0, end_time=1.0
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Setup mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        # CRITICAL: Set corrected_text to refusal text so final_answer gets set correctly
        self.mock_guardrail.validate_response.return_value.corrected_text = (
            "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
        )

        # Setup mock structured output service
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Baserat på GDPR Artikel 6...",
            "kallor": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "Baserat på GDPR Artikel 6..."
        validated_schema.kallor = []
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats...",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        # Setup mock critic - always fails (max 2 attempts)
        self.mock_critic.critique.return_value = CriticResult(
            ok=False,
            fel=["Persistent validation error"],
            atgard="Cannot fix validation issues",
            latency_ms=1.0,
        )

        # Setup mock revise (doesn't really fix anything)
        async def mock_revise(candidate_json, critic_feedback):
            return candidate_json  # Return unchanged

        self.mock_critic.revise.side_effect = mock_revise

        # Execute
        result = await self.orchestrator.process_query(
            question="Vad säger GDPR om personuppgifter?", mode="evidence", enable_reranking=False
        )

        # Assertions
        assert result.success is True
        assert result.mode == ResponseMode.EVIDENCE

        # CRITICAL: Verify EVIDENCE fallback was enforced (refusal template)
        assert "Tyvärr kan jag inte besvara" in result.answer  # Should get refusal
        assert result.metrics.structured_output_enabled is True
        assert result.metrics.critic_revision_count == 2  # C3: 2 revision attempts
        assert not result.metrics.critic_ok  # Final result is still not OK
        # Verify critic was called twice (max attempts)
        assert self.mock_critic.critique.call_count == 2

        # SECURITY: Verify no arbetsanteckning leaked
        assert "arbetsanteckning" not in result.answer

        # Verify empty sources after fallback
        assert len(result.sources) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
