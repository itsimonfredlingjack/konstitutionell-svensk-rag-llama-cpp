"""Smoke test to verify test infrastructure works."""

import pytest


@pytest.mark.unit
class TestSmoke:
    """Verify conftest fixtures load and basic mocks work."""

    def test_mock_config(self, mock_config_service):
        assert mock_config_service.settings.app_name == "Constitutional AI Test"

    def test_mock_llm_service(self, mock_llm_service):
        assert mock_llm_service.is_initialized is True

    def test_mock_retrieval(self, mock_retrieval_service):
        assert mock_retrieval_service.is_initialized is True

    def test_mock_search_results(self, mock_search_results):
        assert len(mock_search_results) == 3
        assert mock_search_results[0].doc_type == "sfs"

    def test_mock_orchestrator_initializes(self, mock_orchestrator):
        assert mock_orchestrator.is_initialized is True
        assert mock_orchestrator.llm_service is not None
        assert mock_orchestrator.retrieval is not None

    @pytest.mark.asyncio
    async def test_mock_llm_streaming(self, mock_llm_service):
        tokens = []
        stats = None
        async for token, s in mock_llm_service.chat_stream(messages=[]):
            if token:
                tokens.append(token)
            else:
                stats = s
        assert "".join(tokens) == "Detta är ett testsvar."
        assert stats.tokens_generated == 42

    @pytest.mark.asyncio
    async def test_mock_retrieval_search(self, mock_retrieval_service):
        result = await mock_retrieval_service.search_with_epr(query="test", k=5)
        assert result.success is True
        assert len(result.results) == 3
