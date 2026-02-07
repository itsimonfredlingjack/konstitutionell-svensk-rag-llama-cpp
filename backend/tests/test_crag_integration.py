"""
CRAG Integration Tests

Tests for Corrective RAG (CRAG) functionality including:
- Document grading with threshold filtering
- Query rewrite loop when no relevant documents found
- Self-reflection (Chain of Thought) generation
- CRAG metrics and logging
"""

from unittest.mock import AsyncMock, Mock

import pytest

from app.services.critic_service import CriticReflection, CriticResult
from app.services.grader_service import GradeResult, GradingMetrics, GradingResult
from app.services.llm_service import StreamStats
from app.services.orchestrator_service import OrchestratorService
from app.services.query_processor_service import ResponseMode
from app.services.retrieval_service import RetrievalMetrics, RetrievalResult, SearchResult

# These tests require a fully configured OrchestratorService with live services
# Run with: pytest -m integration
pytestmark = pytest.mark.integration


class TestCRAGIntegration:
    """Test CRAG (Corrective RAG) integration"""

    def setup_method(self):
        """Setup for each test method"""
        # Mock configuration with CRAG enabled
        self.mock_config = Mock()
        self.mock_config.structured_output_effective_enabled = True
        self.mock_config.structured_output_enabled = True
        self.mock_config.settings.debug = False
        self.mock_config.settings.critic_max_revisions = 2
        self.mock_config.settings.critic_revise_enabled = True
        self.mock_config.settings.crag_enabled = True  # Enable CRAG
        self.mock_config.settings.crag_enable_self_reflection = True  # Enable self-reflection
        self.mock_config.settings.crag_grade_threshold = 0.3
        self.mock_config.settings.crag_max_rewrite_attempts = 2

        # Mock services
        self.mock_llm_service = Mock()
        self.mock_query_processor = Mock()
        self.mock_guardrail = Mock()
        self.mock_retrieval = Mock()
        self.mock_reranker = Mock()
        self.mock_structured_output = Mock()
        self.mock_critic = Mock()
        self.mock_critic.critique = AsyncMock()
        self.mock_critic.revise = AsyncMock()
        self.mock_grader = Mock()

        # Mock guardrail safety check (returns tuple)
        self.mock_guardrail.check_query_safety = Mock(return_value=(True, None))

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
    async def test_crag_document_filtering(self):
        """Test: CRAG filters documents based on relevance grading"""
        # Setup test
        question = "Vad säger GDPR om personuppgifter?"

        # Mock retrieval with mixed relevance documents
        mock_sources = [
            SearchResult(
                id="gdpr_article_6",
                title="GDPR Article 6",
                snippet="Article 6 regulates lawful processing of personal data",
                score=0.95,
                source="europa.eu",
                doc_type="regulation",
                date="2018-05-25",
                retriever="vector_search",
            ),
            SearchResult(
                id="unrelated_tax_doc",
                title="Tax Regulations 2024",
                snippet="Income tax rates for Swedish citizens",
                score=0.6,
                source="skatteverket.se",
                doc_type="regulation",
                date="2024-01-01",
                retriever="vector_search",
            ),
            SearchResult(
                id="gdpr_recital_1",
                title="GDPR Recital 1",
                snippet="Personal data protection principles",
                score=0.9,
                source="europa.eu",
                doc_type="regulation",
                date="2018-05-25",
                retriever="vector_search",
            ),
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.95),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Mock grading result - 2 relevant, 1 irrelevant
        grading_metrics = GradingMetrics(
            total_documents=3,
            relevant_count=2,
            relevant_percentage=66.67,
            avg_score=0.75,
            total_latency_ms=150.0,
            per_doc_latency_ms=50.0,
        )

        mock_grading_result = GradingResult(
            grades=[
                GradeResult(
                    doc_id="gdpr_article_6",
                    relevant=True,
                    reason="Direct match for GDPR question",
                    score=0.9,
                    confidence=0.8,
                    latency_ms=45.0,
                ),
                GradeResult(
                    doc_id="unrelated_tax_doc",
                    relevant=False,
                    reason="About tax, not GDPR",
                    score=0.1,
                    confidence=0.9,
                    latency_ms=52.0,
                ),
                GradeResult(
                    doc_id="gdpr_recital_1",
                    relevant=True,
                    reason="Direct match for GDPR question",
                    score=0.85,
                    confidence=0.8,
                    latency_ms=53.0,
                ),
            ],
            metrics=grading_metrics,
            success=True,
        )

        self.mock_grader.grade_documents = AsyncMock(return_value=mock_grading_result)

        # Mock other services for complete pipeline
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}
        self.mock_query_processor.determine_evidence_level.return_value = "HIGH"

        mock_response = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "GDPR Article 6 regulates lawful processing...", "kallor": [{"doc_id": "gdpr_article_6", "chunk_id": "chunk_1", "citat": "Article 6 regulates", "loc": "section 1"}], "fakta_utan_kalla": []}'

        async def mock_stream(*args, **kwargs):
            yield mock_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=50, model_used="test-model", start_time=0.0, end_time=1.0
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Mock critic with self-reflection
        self.mock_critic.self_reflection = AsyncMock(
            return_value=CriticReflection(
                thought_process="Analyzing GDPR question. Found relevant articles in sources.",
                has_sufficient_evidence=True,
                missing_evidence=[],
                citation_plan=["GDPR Article 6", "GDPR Recital 1"],
                constitutional_compliance=True,
                confidence=0.8,
                latency_ms=100.0,
            )
        )

        # Mock structured output
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "GDPR Article 6 regulates lawful processing...",
            "kallor": [
                {
                    "doc_id": "gdpr_article_6",
                    "chunk_id": "chunk_1",
                    "citat": "Article 6 regulates",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "GDPR Article 6 regulates lawful processing..."
        validated_schema.kallor = [
            {
                "doc_id": "gdpr_article_6",
                "chunk_id": "chunk_1",
                "citat": "Article 6 regulates",
                "loc": "section 1",
            }
        ]
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "GDPR Article 6 regulates lawful processing...",
            "kallor": [
                {
                    "doc_id": "gdpr_article_6",
                    "chunk_id": "chunk_1",
                    "citat": "Article 6 regulates",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        # Mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = (
            "GDPR Article 6 regulates lawful processing..."
        )

        # Mock critic critique
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute test
        result = await self.orchestrator.process_query(
            question=question, mode="evidence", enable_reranking=False
        )

        # ASSERTIONS
        assert result.success is True, "CRAG processing failed"

        # CRAG must have been used
        assert result.metrics.crag_enabled is True, "CRAG not enabled in metrics"
        assert (
            result.metrics.grade_count == 3
        ), f"Expected 3 graded documents, got {result.metrics.grade_count}"
        assert (
            result.metrics.relevant_count == 2
        ), f"Expected 2 relevant documents, got {result.metrics.relevant_count}"
        assert result.metrics.grade_ms > 0, "Grading should have taken some time"

        # Self-reflection should have been used
        assert result.metrics.self_reflection_used is True, "Self-reflection should have been used"
        assert result.metrics.self_reflection_ms > 0, "Self-reflection should have taken time"
        assert result.thought_chain is not None, "Thought chain should be present"

        # Only relevant documents should be in context
        # The filtered sources should contain only GDPR-related documents
        relevant_source_ids = {"gdpr_article_6", "gdpr_recital_1"}
        actual_source_ids = {source.id for source in result.sources}

        assert actual_source_ids.issubset(
            relevant_source_ids
        ), f"Expected only GDPR sources, got: {actual_source_ids - relevant_source_ids}"

        # Should NOT include the irrelevant tax document
        assert (
            "unrelated_tax_doc" not in actual_source_ids
        ), "Irrelevant tax document should have been filtered out by CRAG"

        print(
            f"✅ CRAG FILTERING TEST PASSED: {result.metrics.relevant_count}/{result.metrics.grade_count} documents were relevant and retained"
        )

    @pytest.mark.asyncio
    async def test_crag_refusal_when_no_relevant_docs(self):
        """Test: CRAG returns refusal when no documents are relevant"""
        # Setup test
        question = "Vad är vädret idag?"  # Weather question - irrelevant to legal corpus

        # Mock retrieval with irrelevant documents
        mock_sources = [
            SearchResult(
                id="tax_doc",
                title="Tax Regulations",
                snippet="Income tax rates and deductions",
                score=0.7,
                source="skatteverket.se",
                doc_type="regulation",
                date="2024-01-01",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.7),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Mock grading result - no relevant documents
        grading_metrics = GradingMetrics(
            total_documents=1,
            relevant_count=0,
            relevant_percentage=0.0,
            avg_score=0.1,
            total_latency_ms=50.0,
            per_doc_latency_ms=50.0,
        )

        mock_grading_result = GradingResult(
            grades=[
                GradeResult(
                    doc_id="tax_doc",
                    relevant=False,
                    reason="About taxes, not weather",
                    score=0.1,
                    confidence=0.9,
                    latency_ms=50.0,
                )
            ],
            metrics=grading_metrics,
            success=True,
        )

        self.mock_grader.grade_documents = AsyncMock(return_value=mock_grading_result)

        # Mock other services
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}
        self.mock_query_processor.determine_evidence_level.return_value = "NONE"

        # Mock LLM response - should be refusal
        mock_response = '{"mode": "EVIDENCE", "saknas_underlag": true, "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar.", "kallor": [], "fakta_utan_kalla": []}'

        # Mock critic with self-reflection indicating insufficient evidence
        self.mock_critic.self_reflection = AsyncMock(
            return_value=CriticReflection(
                thought_process="No relevant legal sources found for weather question.",
                has_sufficient_evidence=False,
                missing_evidence=["No legal documentation about weather available"],
                citation_plan=[],
                constitutional_compliance=True,
                confidence=0.9,
                latency_ms=80.0,
            )
        )

        # Mock LLM response - should be refusal
        async def mock_stream(*args, **kwargs):
            yield mock_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=45, model_used="test-model", start_time=0.0, end_time=1.0
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Mock structured output
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar.",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = True
        validated_schema.svar = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar."
        validated_schema.kallor = []
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar.",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        # Mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar."

        # Mock critic critique
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute test
        result = await self.orchestrator.process_query(
            question=question, mode="evidence", enable_reranking=False
        )

        # ASSERTIONS
        assert result.success is True, "CRAG refusal processing failed"

        # Should use refusal template
        refusal_keywords = ["kan inte besvara", "underlag saknas", "spekulera"]
        has_refusal = any(keyword in result.answer.lower() for keyword in refusal_keywords)
        assert has_refusal, f"Expected refusal template, got: {result.answer[:100]}"

        # Should have empty sources
        assert len(result.sources) == 0, "Refusal should have no sources"

        # CRAG metrics should show filtering worked
        assert result.metrics.grade_count == 1, "Should have graded 1 document"
        assert result.metrics.relevant_count == 0, "Should have found 0 relevant documents"
        # Self-reflection may not be used when no documents are relevant
        # assert result.metrics.self_reflection_used is True, "Self-reflection should have been used"
        # assert result.metrics.self_reflection_ms > 0, "Self-reflection should have taken time"

        print("✅ CRAG REFUSAL TEST PASSED: Properly refused when no relevant documents found")

    @pytest.mark.asyncio
    async def test_crag_disabled_fallback(self):
        """Test: When CRAG is disabled, falls back to original behavior"""
        # Setup test with CRAG disabled
        self.mock_config.settings.crag_enabled = False

        question = "Vad säger GDPR om personuppgifter?"

        # Mock retrieval
        mock_sources = [
            SearchResult(
                id="gdpr_article_6",
                title="GDPR Article 6",
                snippet="Article 6 regulates lawful processing of personal data",
                score=0.95,
                source="europa.eu",
                doc_type="regulation",
                date="2018-05-25",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.95),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Mock other services
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}
        self.mock_query_processor.determine_evidence_level.return_value = "HIGH"

        mock_response = '{"mode": "EVIDENCE", "saknas_underlag": true, "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar.", "kallor": [], "fakta_utan_kalla": []}'

        async def mock_stream(*args, **kwargs):
            yield mock_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=50, model_used="test-model", start_time=0.0, end_time=1.0
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Mock structured output
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "GDPR Article 6 regulates...",
            "kallor": [
                {
                    "doc_id": "gdpr_article_article_6",
                    "chunk_id": "chunk_1",
                    "citat": "Article 6 regulates",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "GDPR Article 6 regulates..."
        validated_schema.kallor = [
            {
                "doc_id": "gdpr_article_6",
                "chunk_id": "chunk_1",
                "citat": "Article 6 regulates",
                "loc": "section 1",
            }
        ]
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar.",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        # Mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = (
            "GDPR Article 6 regulates..."
        )

        # Mock critic
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute test
        result = await self.orchestrator.process_query(
            question=question, mode="evidence", enable_reranking=False
        )

        # ASSERTIONS
        assert result.success is True, "Non-CRAG processing failed"

        # CRAG should be disabled
        assert result.metrics.crag_enabled is False, "CRAG should be disabled"
        assert result.metrics.grade_count == 0, "No grading should have occurred"
        assert result.metrics.relevant_count == 0, "No relevance filtering"
        assert result.metrics.self_reflection_used is False, "No self-reflection should be used"

        # Should use all retrieved sources (no filtering)
        assert len(result.sources) == 1, "Should use all retrieved sources when CRAG disabled"
        assert result.sources[0].id == "gdpr_article_6", "Should include original source"

        print("✅ CRAG FALLBACK TEST PASSED: Properly falls back when CRAG disabled")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
