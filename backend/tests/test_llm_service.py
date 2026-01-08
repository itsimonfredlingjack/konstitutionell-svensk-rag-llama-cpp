"""
Integration tests for LLM Service with llama-server (OpenAI-compatible API)
"""

import pytest
import pytest_asyncio

from app.services.llm_service import LLMService, get_llm_service
from app.services.config_service import ConfigService, get_config_service


@pytest_asyncio.fixture
async def config_service():
    """Create config service"""
    return get_config_service()


@pytest_asyncio.fixture
async def llm_service(config_service: ConfigService):
    """Create LLM service"""
    service = get_llm_service(config_service)
    await service.initialize()
    yield service
    await service.close()


class TestLLMServiceLlamaServer:
    """Test LLM Service with llama-server (OpenAI-compatible API)"""

    @pytest.mark.asyncio
    async def test_llm_health_check(self, llm_service: LLMService):
        """Test that llama-server health check works"""
        # Check if llama-server is enabled
        if not llm_service.config.llama_server_enabled:
            pytest.skip("llama-server not enabled in config")

        is_healthy = await llm_service.health_check()
        assert is_healthy is True, "llama-server should be healthy"

    @pytest.mark.asyncio
    async def test_llm_list_models(self, llm_service: LLMService):
        """Test that models can be listed"""
        if not llm_service.config.llama_server_enabled:
            pytest.skip("llama-server not enabled in config")

        models = await llm_service.list_models()
        assert len(models) > 0, "Should have at least one model"
        # Just check that we have at least one model available (don't enforce specific model)
        first_model = models[0]
        model_id = first_model.get("id", "") if isinstance(first_model, dict) else first_model
        assert len(model_id) > 0, "First model should have a non-empty ID"

    @pytest.mark.asyncio
    async def test_llm_stream_chat(self, llm_service: LLMService):
        """Test streaming chat completion"""
        if not llm_service.config.llama_server_enabled:
            pytest.skip("llama-server not enabled in config")

        messages = [{"role": "user", "content": "Say 'Hello World' in one word."}]

        tokens = []
        stats = None

        async for token, final_stats in llm_service.chat_stream(messages):
            if token:
                tokens.append(token)
            if final_stats:
                stats = final_stats

        assert len(tokens) > 0, "Should generate at least one token"
        assert stats is not None, "Should return final stats"
        assert stats.tokens_generated > 0, "Stats should track tokens generated"
        assert stats.total_duration_ms > 0, "Stats should track duration"
        assert stats.tokens_per_second > 0, "Stats should track tokens per second"

    @pytest.mark.asyncio
    async def test_llm_chat_complete(self, llm_service: LLMService):
        """Test non-streaming chat completion"""
        if not llm_service.config.llama_server_enabled:
            pytest.skip("llama-server not enabled in config")

        messages = [{"role": "user", "content": "What is 2+2? Answer with just the number."}]

        full_response, stats = await llm_service.chat_complete(messages)

        assert len(full_response) > 0, "Should generate a response"
        assert "4" in full_response, "Should answer 2+2=4"
        assert stats is not None, "Should return stats"
        assert stats.tokens_generated > 0, "Stats should track tokens"

    @pytest.mark.asyncio
    async def test_llm_with_fallback(self, llm_service: LLMService):
        """Test chat with fallback mechanism"""
        if not llm_service.config.llama_server_enabled:
            pytest.skip("llama-server not enabled in config")

        messages = [{"role": "user", "content": "Test message"}]

        events = []
        async for event, stats in llm_service.chat_with_fallback(messages):
            events.append(event)
            if stats:
                break

        assert len(events) > 0, "Should receive at least one event"
        assert any("token" in event for event in events), "Should receive token events"

    @pytest.mark.asyncio
    async def test_llm_mode_config(self, llm_service: LLMService):
        """Test that mode-specific configurations work"""
        if not llm_service.config.llama_server_enabled:
            pytest.skip("llama-server not enabled in config")

        # Test evidence mode (low temperature)
        messages = [{"role": "user", "content": "Test"}]
        config = llm_service.get_mode_config("evidence")

        full_response, stats = await llm_service.chat_complete(messages, config_override=config)

        assert len(full_response) > 0, "Should generate response with evidence mode config"

    @pytest.mark.asyncio
    async def test_llm_connection_timeout(self, llm_service: LLMService, caplog):
        """Test that connection errors are handled gracefully"""
        if not llm_service.config.llama_server_enabled:
            pytest.skip("llama-server not enabled in config")

        # Use an invalid URL to simulate connection error
        original_base_url = llm_service.config.llama_server_base_url
        llm_service._config.primary_model = "nonexistent-model"

        messages = [{"role": "user", "content": "Test"}]

        try:
            async for token, stats in llm_service.chat_stream(messages):
                pass
            # If we get here without exception, the test should fail
            assert False, "Should have raised an error for nonexistent model"
        except Exception as e:
            # Expected to get an error (model not found or connection error)
            assert (
                "model" in str(e).lower() or "connection" in str(e).lower()
            ), f"Should get model or connection error, got: {e}"
        finally:
            # Restore original config
            llm_service._config.primary_model = llm_service.config.constitutional_model


class TestLLMServiceOllamaFallback:
    """Test LLM Service fallback to default Ollama (port 11434)"""

    @pytest.mark.asyncio
    async def test_default_ollama_connection(self, config_service: ConfigService):
        """Test that default Ollama connection works when llama-server is disabled"""
        # Temporarily disable llama-server
        original_enabled = config_service._settings.llama_server_enabled
        config_service._settings.llama_server_enabled = False

        try:
            service = get_llm_service(config_service)
            await service.initialize()

            # Check if we can connect to default Ollama
            is_connected = await service.is_connected()

            if is_connected:
                # If Ollama is running, test basic operations
                models = await service.list_models()
                assert len(models) > 0, "Should have Ollama models available"

            await service.close()
        finally:
            # Restore original setting
            config_service._settings.llama_server_enabled = original_enabled


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
