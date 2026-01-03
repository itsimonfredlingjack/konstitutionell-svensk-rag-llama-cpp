"""
Pytest Configuration and Fixtures for Constitutional AI Tests
Provides shared fixtures for all tests
"""

import pytest
from pathlib import Path
from typing import Generator, AsyncGenerator

# Test root directory
TEST_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def mock_config():
    """
    Mock configuration for testing.
    
    Returns a ConfigService with test-specific settings.
    """
    from app.services.config_service import ConfigService, ConfigSettings
    from pydantic_settings import SettingsConfigDict
    
    # Create test config with mock paths
    test_settings = ConfigSettings(
        model_config=SettingsConfigDict(
            env_file="tests/.env.test",
            env_file_encoding="utf-8",
            env_prefix="CONST_",
            extra="ignore",
        ),
        # Override paths for testing
        chromadb_path=str(TEST_ROOT / "test_data" / "chromadb_test"),
        pdf_cache_path=str(TEST_ROOT / "test_data" / "pdf_cache_test"),
        # Disable expensive features in tests
        use_mock_data=True,
        reranking_enabled=False,  # Don't load BGE in tests
        adaptive_retrieval_enabled=False,
        # Fast timeouts for tests
        llm_timeout=5.0,
        search_timeout=1.0,
    )
    
    # Create service with test settings
    class TestConfigService(ConfigService):
        def __init__(self):
            self._settings = test_settings
    
    return TestConfigService()


@pytest.fixture
def mock_chroma_client():
    """
    Mock ChromaDB client for testing.
    
    Returns a mock that simulates ChromaDB behavior.
    """
    from unittest.mock import MagicMock
    
    mock = MagicMock()
    mock.list_collections.return_value = []
    mock.get_collection.return_value = MagicMock()
    
    return mock


@pytest.fixture
def mock_ollama_client():
    """
    Mock Ollama client for testing.
    
    Returns a mock that simulates Ollama API calls.
    """
    from unittest.mock import MagicMock, AsyncMock
    
    mock = MagicMock()
    mock.is_connected = AsyncMock(return_value=True)
    mock.list_models = AsyncMock(return_value=["ministral-3:14b", "gpt-sw3:6.7b"])
    mock.list_running_models = AsyncMock(return_value=[])
    
    # Mock streaming response
    async def mock_chat_stream(*args, **kwargs):
        """Mock streaming chat response"""
        import asyncio
        
        response_text = "Mock LLM response"
        for char in response_text:
            yield char, None
        yield "", None  # Final signal
    
    mock.chat_stream = mock_chat_stream
    
    return mock


@pytest.fixture
def mock_embedding_service():
    """
    Mock embedding service for testing.
    
    Returns a mock that generates fake embeddings.
    """
    import numpy as np
    from unittest.mock import MagicMock
    
    mock = MagicMock()
    
    # Generate fake 768-dim embeddings
    def mock_embed(texts):
        return np.random.randn(len(texts), 768).tolist()
    
    mock.embed = mock_embed
    mock.embed_single = lambda text: np.random.randn(768).tolist()
    mock.get_dimension.return_value = 768
    
    return mock


@pytest.fixture
async def initialized_services(mock_config):
    """
    Fixture that provides initialized services.
    
    Yields a dictionary of initialized service instances.
    """
    from app.services.config_service import ConfigService
    from app.services.base_service import BaseService
    from app.services.llm_service import LLMService
    
    # Use real config service
    config = ConfigService()
    
    # Create services
    llm_service = LLMService(config)
    
    # Initialize services
    await llm_service.initialize()
    
    try:
        yield {
            "config": config,
            "llm_service": llm_service,
        }
    finally:
        # Cleanup
        await llm_service.close()


@pytest.fixture
def sample_query():
    """Sample query for testing"""
    return "Vad säger GDPR om personuppgifter?"


@pytest.fixture
def sample_document():
    """Sample document for testing"""
    return {
        "id": "doc_001",
        "title": "Test Document",
        "content": "This is a test document about GDPR.",
        "metadata": {
            "doc_type": "sfs",
            "source": "test",
            "date": "2025-01-01",
        },
    }


@pytest.fixture
def sample_search_results():
    """Sample search results for testing"""
    return [
        {
            "id": "doc_001",
            "title": "GDPR Article 17",
            "snippet": "Right to rectification...",
            "score": 0.92,
            "doc_type": "sfs",
            "source": "sfs_lagtext",
        },
        {
            "id": "doc_002",
            "title": "GDPR Article 18",
            "snippet": "Right to restriction of processing...",
            "score": 0.85,
            "doc_type": "sfs",
            "source": "sfs_lagtext",
        },
    ]


@pytest.fixture
def sample_conversation_history():
    """Sample conversation history for testing"""
    return [
        {"role": "user", "content": "Hej!"},
        {"role": "assistant", "content": "Hej! Hur kan jag hjälpa dig?"},
    ]


def pytest_configure(config):
    """
    Pytest configuration hook.
    
    Registers custom markers and config.
    """
    # Register custom markers
    config.addinivalue(
        "integration",
        "marks tests as integration tests (requires real services)",
    )
    config.addinivalue(
        "unit",
        "marks tests as unit tests (uses mocks)",
    )
    config.addinivalue(
        "slow",
        "marks tests as slow (skip by default)",
    )
    
    # Skip slow tests by default
    config.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run slow tests",
    )

