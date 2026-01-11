"""
Pytest Configuration and Fixtures for Constitutional AI Tests
Provides shared fixtures for all tests
"""

import os
import socket
import sys
from pathlib import Path

import pytest

# Repo root directory
REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT

# Add backend to Python path for imports (so `import app...` works)
backend_root = REPO_ROOT / "backend"
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


def _env_truthy(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _port_open(host: str, port: int, timeout_s: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _run_integration_tests() -> bool:
    return _env_truthy("RUN_INTEGRATION_TESTS")


def _run_ollama_tests() -> bool:
    return _env_truthy("RUN_OLLAMA_TESTS")


def is_ollama_available(host: str = "127.0.0.1", port: int = 11434) -> bool:
    return _port_open(host, port)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    # Enforce test pyramid: integration tests are opt-in.
    if item.get_closest_marker("integration") and not _run_integration_tests():
        pytest.skip("Integration tests are opt-in; set RUN_INTEGRATION_TESTS=1")

    # "No Ollama" policy: Ollama-dependent tests are opt-in AND require Ollama running.
    if item.get_closest_marker("ollama"):
        if not _run_ollama_tests():
            pytest.skip("Ollama tests are opt-in; set RUN_OLLAMA_TESTS=1")
        if not is_ollama_available():
            pytest.skip("Ollama is not running on localhost:11434")


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
        chromadb_path=str(REPO_ROOT / "test_data" / "chromadb_test"),
        pdf_cache_path=str(REPO_ROOT / "test_data" / "pdf_cache_test"),
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
    from unittest.mock import AsyncMock, MagicMock

    mock = MagicMock()
    mock.is_connected = AsyncMock(return_value=True)
    mock.list_models = AsyncMock(return_value=["ministral-3:14b", "gpt-sw3:6.7b"])
    mock.list_running_models = AsyncMock(return_value=[])

    # Mock streaming response
    async def mock_chat_stream(*args, **kwargs):
        """Mock streaming chat response"""

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
    from unittest.mock import MagicMock

    import numpy as np

    mock = MagicMock()

    # Generate fake 768-dim embeddings
    def mock_embed(texts):
        return np.random.randn(len(texts), 768).tolist()

    mock.embed = mock_embed
    mock.embed_single = lambda text: np.random.randn(768).tolist()
    mock.get_dimension.return_value = 768

    return mock


@pytest.fixture
async def initialized_services(mock_config, request):
    """
    Fixture that provides initialized services.

    Yields a dictionary of initialized service instances.
    """
    # This fixture initializes a real LLM service and is therefore integration-like.
    if not _run_integration_tests() and not request.node.get_closest_marker("integration"):
        pytest.skip(
            "initialized_services requires integration; set RUN_INTEGRATION_TESTS=1 or mark test @pytest.mark.integration"
        )

    from app.services.config_service import ConfigService
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
    # Marker declarations live in `pyproject.toml`; keep this hook minimal and stable.
    return
