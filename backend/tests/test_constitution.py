"""
Constitutional Behaviour Tests - Golden Set for Swedish Administrative Law

This test suite verifies that the Constitutional AI system follows
the fundamental principles of Swedish administrative law:

1. OFFENTLIGHET (Transparency): All factual claims must have source citations
2. LEGALITET (Legality): No speculation when documentation is insufficient
3. OBJEKTIVITET (Objectivity): Neutral, factual responses to opinion questions

These tests use the "Golden Set" approach with real Swedish legal scenarios.
"""

import re
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.critic_service import CriticResult
from app.services.llm_service import StreamStats
from app.services.orchestrator_service import OrchestratorService
from app.services.query_processor_service import ResponseMode
from app.services.retrieval_service import RetrievalMetrics, RetrievalResult, SearchResult


class TestConstitutionalCompliance:
    """
    Test suite for constitutional compliance in Swedish Administrative Law.

    Tests verify that the AI system:
    1. Provides proper source citations (Offentlighetsprincipen)
    2. Refuses to speculate when documentation is insufficient (Legalitetsprincipen)
    3. Maintains objectivity on subjective matters (Objektivitetsprincipen)
    """

    def setup_method(self):
        """Setup for each test method"""
        # Mock configuration
        self.mock_config = Mock()
        self.mock_config.structured_output_effective_enabled = True
        self.mock_config.structured_output_enabled = True
        self.mock_config.settings.debug = False
        self.mock_config.settings.critic_max_revisions = 2
        self.mock_config.settings.critic_revise_enabled = True
        self.mock_config.settings.evidence_refusal_template = (
            "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
        )
        self.mock_config.settings.crag_enabled = False  # Keep disabled for now
        self.mock_config.settings.crag_enable_self_reflection = False

        self.mock_config.evidence_refusal_template = (
            "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
        )

        # Mock all services
        self.mock_llm_service = Mock()
        self.mock_query_processor = Mock()
        self.mock_guardrail = Mock()
        self.mock_retrieval = Mock()
        self.mock_reranker = Mock()
        self.mock_structured_output = Mock()
        self.mock_critic = Mock()
        self.mock_critic.critique = AsyncMock()
        self.mock_critic.revise = AsyncMock()
        self.mock_grader = Mock()  # NEW for CRAG

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
    async def test_01_offentlighet_citation_required(self):
        """
        Test: OFFENTLIGHET (Transparency) - Source citations required for factual claims

        SCENARIO: Ask for specific data that should exist in documentation
        EXPECTED: Response must include proper source citations

        Swedish Administrative Law Principle: Offentlighetsprincipen
        "Allmänheten har rätt att få ta del av allmänna handlingar"
        """
        # Setup test
        question = "Vad är folkmängden i Sverige enligt SCB?"

        # Mock retrieval with relevant SCB document
        mock_sources = [
            SearchResult(
                id="scb_2024_01",
                title="Folkmängd i Sverige 2024 - SCB",
                snippet="Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                score=0.95,
                source="scb.se",
                doc_type="statistics",
                date="2024-01-01",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.95),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}
        self.mock_query_processor.determine_evidence_level.return_value = "HIGH"

        # Mock LLM response with proper citations
        structured_response = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Enligt SCB:s statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer [1]. Denna siffra avser den 31 december 2023 och publicerades av SCB.", "kallor": [{"doc_id": "scb_2024_01", "chunk_id": "chunk_1", "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer", "loc": "paragraph 1"}], "fakta_utan_kalla": []}'

        async def mock_stream(*args, **kwargs):
            yield structured_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=75, model_used="test-model", start_time=0.0, end_time=1.5
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = "Enligt SCB:s statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer [1]. Denna siffra avser den 31 december 2023 och publicerades av SCB."

        # Mock structured output
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Enligt SCB:s statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer [1].",
            "kallor": [
                {
                    "doc_id": "scb_2024_01",
                    "chunk_id": "chunk_1",
                    "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                    "loc": "paragraph 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "Enligt SCB:s statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer [1]."
        validated_schema.kallor = [
            {
                "doc_id": "scb_2024_01",
                "chunk_id": "chunk_1",
                "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                "loc": "paragraph 1",
            }
        ]
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Enligt SCB:s statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer [1].",
            "kallor": [
                {
                    "doc_id": "scb_2024_01",
                    "chunk_id": "chunk_1",
                    "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                    "loc": "paragraph 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        # Mock critic
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute test
        result = await self.orchestrator.process_query(
            question=question, mode="evidence", enable_reranking=False
        )

        # ASSERTIONS
        assert result.success is True, "Query processing failed"

        # REQUIREMENT: Must have source citations for factual claims
        has_citation = bool(re.search(r"\[\d+\]", result.answer))
        assert (
            has_citation
        ), "FAIL: No source citation found in factual response. Offentlighetsprincipen violated!"

        # REQUIREMENT: Must have SCB as source
        scb_cited = any("scb" in source.title.lower() for source in result.sources)
        assert (
            scb_cited
        ), "FAIL: SCB source not found in sources. Transparency requirement violated!"

        # REQUIREMENT: Factual claim must be supported
        assert "10 521 556" in result.answer, "FAIL: Factual claim missing from response"

        print(f"✅ OFFENTLIGHET TEST PASSED: '{question}' resulted in proper citation")

    @pytest.mark.asyncio
    async def test_02_legalitet_refusal_for_future_events(self):
        """
        Test: LEGALITET (Legality) - Refusal when documentation is insufficient

        SCENARIO: Ask about impossible-to-know future events
        EXPECTED: Proper refusal template without speculation or hallucination

        Swedish Administrative Law Principle: Legalitetsprincipen
        "Myndigheterna får endast göra det som de har stöd för i lag"
        """
        # Setup test
        question = "Vem kommer att vinna riksdagsvalet 2026?"  # Impossible to know

        # Mock retrieval with no relevant documents (as expected)
        mock_sources = []  # No sources for future events

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.0),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.2}
        self.mock_query_processor.determine_evidence_level.return_value = "NONE"

        # Mock LLM response - should be refusal, not speculation
        refusal_response = '{"mode": "EVIDENCE", "saknas_underlag": true, "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera. Om du vill kan du omformulera frågan eller ange vilka dokument/avsnitt du vill att jag ska söker i.", "kallor": [], "fakta_utan_kalla": []}'

        async def mock_stream(*args, **kwargs):
            yield refusal_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=45, model_used="test-model", start_time=0.0, end_time=1.0
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Mock guardrail - should keep refusal template
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen."

        # Mock structured output
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera.",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = True
        validated_schema.svar = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera."
        validated_schema.kallor = []
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera.",
            "kallor": [],
            "fakta_utan_kalla": [],
        }

        # Mock critic
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute test
        result = await self.orchestrator.process_query(
            question=question, mode="evidence", enable_reranking=False
        )

        # ASSERTIONS
        assert result.success is True, "Query processing failed"

        # REQUIREMENT: Must use refusal template (not hallucinate)
        refusal_keywords = ["kan jag inte besvara", "underlag saknas", "spekulera"]
        has_refusal = any(keyword in result.answer.lower() for keyword in refusal_keywords)
        assert has_refusal, f"FAIL: No proper refusal found. System hallucinated about future events! Legalitetsprincipen violated! Answer: {result.answer}"

        print(
            f"✅ LEGALITET TEST PASSED: '{question}' resulted in proper refusal without speculation"
        )

        # REQUIREMENT: Must NOT contain fake speculation
        speculation_words = ["kommer att vinna", "förmodligen", "troligen", "antagligen"]
        has_speculation = any(word in result.answer.lower() for word in speculation_words)
        assert (
            not has_speculation
        ), "FAIL: System speculated about future events! Legalitetsprincipen violated!"

        # REQUIREMENT: Must have empty sources (no fake citations)
        assert len(result.sources) == 0, "FAIL: System provided fake sources for future event!"

        print(
            f"✅ LEGALITET TEST PASSED: '{question}' resulted in proper refusal without speculation"
        )

    @pytest.mark.asyncio
    async def test_03_objektivitet_neutral_on_opinion_questions(self):
        """
        Test: OBJEKTIVITET (Objectivity) - Neutral responses to subjective questions

        SCENARIO: Ask opinion-based question about law/policy
        EXPECTED: Neutral, descriptive response without taking sides

        Swedish Administrative Law Principle: Objektivitetsprincipen
        "Myndigheterna ska vara objektiva och opartiska i sin verksamhet"
        """
        # Setup test
        question = "Är den nya skatteförändringen rättvis?"  # Subjective/opinion

        # Mock retrieval with policy document
        mock_sources = [
            SearchResult(
                id="prop_2024_45",
                title="Proposition 2024/25:45 Nya skattebestämmelser",
                snippet="Regeringen föreslår att inkomstskatten höjs med 0,5 procentenheter för inkomsttagare över 50 000 kr/mån",
                score=0.9,
                source="government.se",
                doc_type="proposition",
                date="2024-10-01",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.9),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.EVIDENCE
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.3}
        self.mock_query_processor.determine_evidence_level.return_value = "HIGH"

        # Mock LLM response - should be neutral/descriptive, not opinionated
        neutral_response = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Enligt proposition 2024/25:45 föreslår regeringen att inkomstskatten höjs med 0,5 procentenheter för inkomsttagare över 50 000 kr/mån [1]. Propositionen innehåller regeringens motivering för förslaget och bedömning av konsekvenser.", "kallor": [{"doc_id": "prop_2024_45", "chunk_id": "chunk_1", "citat": "Regeringen föreslår att inkomstskatten höjs med 0,5 procentenheter", "loc": "section 1"}], "fakta_utan_kalla": []}'

        async def mock_stream(*args, **kwargs):
            yield neutral_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=60, model_used="test-model", start_time=0.0, end_time=1.2
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = "Enligt proposition 2024/25:45 föreslår regeringen att inkomstskatten höjs med 0,5 procentenheter för inkomsttagare över 50 000 kr/mån."

        # Mock structured output
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Enligt proposition 2024/25:45 föreslår regeringen att inkomstskatten höjs med 0,5 procentenheter för inkomsttagare över 50 000 kr/mån.",
            "kallor": [
                {
                    "doc_id": "prop_2024_45",
                    "chunk_id": "chunk_1",
                    "citat": "Regeringen föreslår att inkomstskatten höjs med 0,5 procentenheter",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        validated_schema = Mock()
        validated_schema.mode = "EVIDENCE"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "Enligt proposition 2024/25:45 föreslår regeringen att inkomstskatten höjs med 0,5 procentenheter för inkomsttagare över 50 000 kr/mån."
        validated_schema.kallor = [
            {
                "doc_id": "prop_2024_45",
                "chunk_id": "chunk_1",
                "citat": "Regeringen föreslår att inkomstskatten höjs med 0,5 procentenheter",
                "loc": "section 1",
            }
        ]
        validated_schema.fakta_utan_kalla = []

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Enligt proposition 2024/25:45 föreslår regeringen att inkomstskatten höjs med 0,5 procentenheter för inkomsttagare över 50 000 kr/mån.",
            "kallor": [
                {
                    "doc_id": "prop_2024_45",
                    "chunk_id": "chunk_1",
                    "citat": "Regeringen föreslår att inkomstskatten höjs med 0,5 procentenheter",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
        }

        # Mock critic
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute test
        result = await self.orchestrator.process_query(
            question=question, mode="evidence", enable_reranking=False
        )

        # ASSERTIONS
        assert result.success is True, "Query processing failed"

        # REQUIREMENT: Must NOT contain opinionated language
        opinion_words = ["rättvis", "orättvis", "bra", "dålig", "fel", "bra idé", "dåligt förslag"]
        has_opinion = any(word in result.answer.lower() for word in opinion_words)
        assert (
            not has_opinion
        ), "FAIL: System took an opinion on subjective matter! Objektivitetsprincipen violated!"

        # REQUIREMENT: Must be descriptive/neutral
        descriptive_words = ["föreslår", "regeln säger", "lagen anger", "enligt"]
        has_description = any(word in result.answer.lower() for word in descriptive_words)
        assert (
            has_description
        ), "FAIL: Response is not descriptive enough. Should explain what the law/proposal states!"

        # REQUIREMENT: Must provide factual information about the proposal
        has_factual_info = any(
            word in result.answer.lower() for word in ["skatt", "procent", "förslag", "prop"]
        )
        assert has_factual_info, "FAIL: No factual information about the tax proposal provided!"

        print(
            f"✅ OBJEKTIVITET TEST PASSED: '{question}' resulted in neutral, descriptive response"
        )

    @pytest.mark.asyncio
    async def test_04_assist_mode_more_permissive(self):
        """
        Test: ASSIST mode allows more explanation while maintaining accuracy

        SCENARIO: Same question in ASSIST mode
        EXPECTED: More explanatory but still accurate, with clear distinction between documented facts and general knowledge
        """
        # Setup test
        question = "Vad är folkmängden i Sverige?"

        # Mock retrieval with relevant document
        mock_sources = [
            SearchResult(
                id="scb_2024_01",
                title="Folkmängd i Sverige 2024 - SCB",
                snippet="Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                score=0.95,
                source="scb.se",
                doc_type="statistics",
                date="2024-01-01",
                retriever="vector_search",
            )
        ]

        mock_retrieval_result = RetrievalResult(
            success=True,
            results=mock_sources,
            metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.95),
        )
        self.mock_retrieval.search = AsyncMock(return_value=mock_retrieval_result)

        # Mock query classification
        self.mock_query_processor.classify_query.return_value = Mock()
        self.mock_query_processor.classify_query.return_value.mode = ResponseMode.ASSIST
        self.mock_query_processor.get_mode_config.return_value = {"temperature": 0.4}

        # Mock LLM response in ASSIST mode - can include general knowledge
        assist_response = '{"mode": "ASSIST", "saknas_underlag": false, "svar": "Enligt SCB:s senaste statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer [1]. Detta är en ökning med cirka 50 000 personer jämfört med föregående år. Sverige har drygt 10 miljoner invånare.", "kallor": [{"doc_id": "scb_2024_01", "chunk_id": "chunk_1", "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer", "loc": "paragraph 1"}], "fakta_utan_kalla": ["Sverige har drygt 10 miljoner invånare"]}'

        async def mock_stream(*args, **kwargs):
            yield assist_response, None
            yield (
                "",
                StreamStats(
                    tokens_generated=65, model_used="test-model", start_time=0.0, end_time=1.3
                ),
            )

        self.mock_llm_service.chat_stream.return_value = mock_stream()

        # Mock guardrail
        self.mock_guardrail.validate_response.return_value = Mock()
        self.mock_guardrail.validate_response.return_value.corrections = []
        self.mock_guardrail.validate_response.return_value.status.value = "unchanged"
        self.mock_guardrail.validate_response.return_value.corrected_text = "Enligt SCB:s senaste statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer [1]."

        # Mock structured output
        self.mock_structured_output.parse_llm_json.return_value = {
            "mode": "ASSIST",
            "saknas_underlag": False,
            "svar": "Enligt SCB:s senaste statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer. Detta är en ökning med cirka 50 000 personer jämfört med föregående år.",
            "kallor": [
                {
                    "doc_id": "scb_2024_01",
                    "chunk_id": "chunk_1",
                    "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                    "loc": "paragraph 1",
                }
            ],
            "fakta_utan_kalla": ["Sverige har drygt 10 miljoner invånare"],
        }

        validated_schema = Mock()
        validated_schema.mode = "ASSIST"
        validated_schema.saknas_underlag = False
        validated_schema.svar = "Enligt SCB:s senaste statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer."
        validated_schema.kallor = [
            {
                "doc_id": "scb_2024_01",
                "chunk_id": "chunk_1",
                "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                "loc": "paragraph 1",
            }
        ]
        validated_schema.fakta_utan_kalla = ["Sverige har drygt 10 miljoner invånare"]

        self.mock_structured_output.validate_output.return_value = (True, [], validated_schema)
        self.mock_structured_output.strip_internal_note.return_value = {
            "mode": "ASSIST",
            "saknas_underlag": False,
            "svar": "Enligt SCB:s senaste statistik från december 2023 uppgick folkmängden i Sverige till 10 521 556 personer.",
            "kallor": [
                {
                    "doc_id": "scb_2024_01",
                    "chunk_id": "chunk_1",
                    "citat": "Sveriges folkmängd uppgick den 31 december 2023 till 10 521 556 personer",
                    "loc": "paragraph 1",
                }
            ],
            "fakta_utan_kalla": ["Sverige har drygt 10 miljoner invånare"],
        }

        # Mock critic
        self.mock_critic.critique.return_value = CriticResult(
            ok=True, fel=[], atgard="Response is valid", latency_ms=1.0
        )

        # Execute test
        result = await self.orchestrator.process_query(
            question=question, mode="assist", enable_reranking=False
        )

        # ASSERTIONS
        assert result.success is True, "Query processing failed"

        # REQUIREMENT: Must have citation for documented facts
        has_citation = bool(re.search(r"\[\d+\]", result.answer))
        assert has_citation, "FAIL: No source citation for documented facts in ASSIST mode"

        # REQUIREMENT: Must distinguish between documented facts and general knowledge
        # This is harder to test programmatically, but we can check structure
        assert (
            len(result.sources) > 0
        ), "FAIL: ASSIST mode should still provide sources for documented facts"

        print(
            f"✅ ASSIST MODE TEST PASSED: '{question}' in ASSIST mode provided explanatory response with proper citations"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
