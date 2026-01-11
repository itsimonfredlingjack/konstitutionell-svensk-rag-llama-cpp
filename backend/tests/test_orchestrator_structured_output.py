"""
Tests for Orchestrator Service with Structured Output Integration
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.llm_service import StreamStats
from app.services.orchestrator_service import OrchestratorService
from app.services.query_processor_service import ResponseMode
from app.services.retrieval_service import RetrievalMetrics, RetrievalResult, SearchResult


class TestOrchestratorStructuredOutput:
    """Test cases for orchestrator integration with structured output"""

    def setup_method(self):
        """Setup for each test method"""
        # Mock all dependencies
        self.mock_config = Mock()
        self.mock_config.structured_output_effective_enabled = True
        self.mock_config.structured_output_enabled = True
        self.mock_config.settings.debug = False
        self.mock_config.settings.crag_enabled = False
        self.mock_config.critic_revise_effective_enabled = (
            False  # Disable critic to avoid Mock comparisons
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
        self.mock_grader = Mock()

        # Set async methods to AsyncMock for all services
        for mock_service in [
            self.mock_llm_service,
            self.mock_query_processor,
            self.mock_guardrail,
            self.mock_retrieval,
            self.mock_reranker,
            self.mock_structured_output,
            self.mock_critic,
            self.mock_grader,
        ]:
            mock_service.initialize = AsyncMock()
            mock_service.close = AsyncMock()

        # Set common async methods
        self.mock_retrieval.search = AsyncMock()
        self.mock_grader.grade_documents = AsyncMock()
        self.mock_critic.self_reflection = AsyncMock()
        self.mock_critic.critique = AsyncMock()
        self.mock_critic.revise = AsyncMock()
        self.mock_reranker.rerank = AsyncMock()
        # self.mock_llm_service.chat_stream = AsyncMock()  # Tests set this specifically
        self.mock_structured_output.parse_llm_json = Mock()  # Not async
        self.mock_structured_output.validate_output = Mock()  # Not async
        self.mock_structured_output.strip_internal_note = Mock()  # Not async

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
            grader=self.mock_grader,
        )

    @pytest.mark.asyncio
    async def test_it1_evidence_with_sources_success(self):
        """IT1: EVIDENCE + sources + structured JSON → verify success, sources in result, no arbetsanteckningar"""
        # NOTE: Now handled in setup_method

        # Initialize orchestrator
        await self.orchestrator.initialize()

        # Setup mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}

        # Setup mock retrieval with relevant documents (FIX: Use AsyncMock)
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
        structured_response = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Baserat på GDPR Artikel 6 så regleras laglig behandling av personuppgifter...", "kallor": [{"doc_id": "gdpr_doc_1", "chunk_id": "chunk_1", "citat": "Article 6 regulates lawful processing", "loc": "section 1"}], "fakta_utan_kalla": [], "arbetsanteckning": "Internal control note"}'

        # Mock streaming LLM response (FIX: Use correct StreamStats structure)
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
        # FIX: corrected_text should be the final answer text (svar), NOT the full JSON
        self.mock_guardrail.validate_response.return_value.corrected_text = (
            "Baserat på GDPR Artikel 6 så regleras laglig behandling av personuppgifter..."
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
            "arbetsanteckning": "Internal control note",
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
        validated_schema.arbetsanteckning = "Internal control note"

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

        # Execute
        result = await self.orchestrator.process_query(
            question="Vad säger GDPR om personuppgifter?",
            mode="evidence",
            enable_reranking=False,  # FIX: Disable reranking to avoid async reranker.rerank() call
        )

        # Assertions
        assert result.success is True
        assert result.mode == ResponseMode.EVIDENCE
        assert "GDPR" in result.answer
        assert len(result.sources) > 0
        assert result.sources[0].id == "gdpr_doc_1"
        assert result.metrics.structured_output_enabled is True
        # Security assertion: arbetsanteckningar should not leak into result.answer
        assert "arbetsanteckning" not in result.answer

    @pytest.mark.asyncio
    async def test_it2_evidence_no_sources_refusal(self):
        """IT2: EVIDENCE + no sources → refusal (saknas_underlag=True) → verify success and empty sources"""
        # NOTE: AsyncMock setup now handled in setup_method

        # Initialize orchestrator
        await self.orchestrator.initialize()

        # Setup mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}

        # Setup mock retrieval with no relevant documents (FIX: Use AsyncMock)
        mock_sources = []
        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="adaptive", top_score=0.1),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Setup mock LLM response that returns refusal
        refusal_response = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen..."

        # Mock streaming LLM response (FIX: Use correct StreamStats structure)
        async def mock_stream(*args, **kwargs):
            yield refusal_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=30, model_used="test-model", start_time=0.0, end_time=0.6
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Setup mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = refusal_response

        # Setup mock structured output service for refusal
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": refusal_response,
            "kallor": [],
            "fakta_utan_kalla": [],
            "arbetsanteckning": "Refusal due to lack of supporting documents",
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = True
        validated_schema.svar = refusal_response
        validated_schema.kallor = []
        validated_schema.fakta_utan_kalla = []
        validated_schema.arbetsanteckning = "Refusal due to lack of supporting documents"

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": refusal_response,
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        # Execute
        result = await self.orchestrator.process_query(
            question="Vad säger lagen om kvantumkryptering på Mars?",
            mode="evidence",
            enable_reranking=False,  # FIX: Disable reranking to avoid async reranker.rerank() call
        )

        # Assertions
        assert result.success is True
        assert result.mode == ResponseMode.EVIDENCE
        assert "Tyvärr kan jag inte besvara" in result.answer
        assert len(result.sources) == 0
        assert result.metrics.parse_errors is False

    @pytest.mark.asyncio
    async def test_it3_invalid_json_retry_then_success(self):
        """IT3: Invalid JSON attempt1 + valid JSON attempt2 → verify retry (call_count==2) and safe output"""
        # NOTE: AsyncMock setup now handled in setup_method

        # Initialize orchestrator
        await self.orchestrator.initialize()

        call_count = 0

        # Setup mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}

        # Setup mock retrieval (FIX: Use AsyncMock)
        mock_sources = [
            SearchResult(
                id="test_doc",
                title="Test",
                snippet="Test content",
                score=0.8,
                source="test",
                doc_type="law",
                date="2023-01-01",
                retriever="test",
            )
        ]
        self.mock_retrieval.search = AsyncMock(
            return_value=RetrievalResult(
                success=True,
                results=mock_sources,
                metrics=RetrievalMetrics(strategy="adaptive", top_score=0.8),
            )
        )

        # Setup mock LLM that fails on first attempt, succeeds on retry (FIX: Use correct StreamStats structure)
        # FIX: Use side_effect to return fresh generator each time
        def create_mock_stream():
            async def mock_stream():
                nonlocal call_count
                call_count += 1

                if call_count == 1:
                    # First attempt - invalid JSON
                    yield '{"mode": "EVIDENCE", invalid json', None
                else:
                    # Second attempt (retry) - valid JSON
                    yield (
                        '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Success after retry", "kallor": [], "fakta_utan_kalla": []}',
                        None,
                    )

                yield (
                    "",
                    StreamStats(
                        tokens_generated=20, model_used="test-model", start_time=0.0, end_time=0.5
                    ),
                )

            return mock_stream()

        # FIX: Use side_effect with lambda to create fresh generator for each call
        self.mock_llm_service.chat_stream.side_effect = lambda *a, **k: create_mock_stream()

        # Setup mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = "Success after retry"

        # Setup mock structured output service
        self.mock_structured_output.parse_llm_json.side_effect = [
            json.JSONDecodeError("Invalid JSON", "attempt 1", 0),  # First attempt fails
            {  # Second attempt succeeds
                "mode": "EVIDENCE",
                "saknas_underlag": False,
                "svar": "Success after retry",
                "kallor": [],
                "fakta_utan_kalla": [],
                "arbetsanteckning": "Internal note",
            },
        ]

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "Success after retry"
        validated_schema.kallor = []
        validated_schema.fakta_utan_kalla = []
        validated_schema.arbetsanteckning = "Internal note"

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Success after retry",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        # Execute
        result = await self.orchestrator.process_query(
            question="Test question?",
            mode="evidence",
            enable_reranking=False,  # FIX: Disable reranking to avoid async reranker.rerank() call
        )

        # Assertions
        assert result.success is True
        assert "Success after retry" in result.answer
        assert call_count == 2  # Should have called LLM twice (original + retry)
        # parse_errors=True is correct since attempt 1 failed (even though retry succeeded)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
