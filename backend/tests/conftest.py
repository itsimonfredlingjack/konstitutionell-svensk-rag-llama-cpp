"""
Pytest configuration and shared fixtures for Constitutional AI backend tests.

Provides:
- Mock ChromaDB, LLM, and service fixtures for unit testing
- FastAPI TestClient with dependency overrides
- Marker-based test gating (integration, ollama, slow)

Usage:
    pytest tests/ -v -m unit          # Unit tests only (no network)
    pytest tests/ -v -m integration   # Integration tests (requires services)
"""

import os
import socket
import sys
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add parent directory (backend/) to Python path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


# ═══════════════════════════════════════════════════════════════════
# TEST MARKERS & HOOKS
# ═══════════════════════════════════════════════════════════════════


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


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


def pytest_configure(config):
    """Register backend test markers."""
    config.addinivalue_line(
        "markers",
        "integration: requires external services; opt-in via RUN_INTEGRATION_TESTS=1",
    )
    config.addinivalue_line(
        "markers",
        "ollama: requires a running Ollama instance; opt-in via RUN_OLLAMA_TESTS=1",
    )
    config.addinivalue_line("markers", "unit: pure unit tests (no network/GPU)")
    config.addinivalue_line("markers", "slow: slow tests")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """Default-safe: skip integration/ollama tests unless explicitly enabled."""
    if item.get_closest_marker("integration") and not _run_integration_tests():
        pytest.skip("Integration tests are opt-in; set RUN_INTEGRATION_TESTS=1")

    if item.get_closest_marker("ollama"):
        if not _run_ollama_tests():
            pytest.skip("Ollama tests are opt-in; set RUN_OLLAMA_TESTS=1")
        if not is_ollama_available():
            pytest.skip("Ollama is not running on localhost:11434")


def is_ollama_available(host: str = "127.0.0.1", port: int = 11434) -> bool:
    """Returns True only when Ollama tests are enabled AND the service is reachable."""
    return _run_ollama_tests() and _port_open(host, port)


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    """Fixture that returns True if Ollama is enabled and reachable."""
    return is_ollama_available()


# ═══════════════════════════════════════════════════════════════════
# MOCK CONFIG SERVICE
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_config_settings():
    """Test-safe ConfigSettings with no external dependencies."""
    settings = MagicMock()
    settings.app_name = "Constitutional AI Test"
    settings.app_version = "2.0.0-test"
    settings.debug = True
    settings.host = "127.0.0.1"
    settings.port = 8900
    settings.chromadb_path = "/tmp/test_chromadb"
    settings.pdf_cache_path = "/tmp/test_pdf_cache"
    settings.default_collections = ["test_collection"]
    settings.embedding_model = "jinaai/jina-embeddings-v3"
    settings.expected_embedding_dim = 1024
    settings.llm_base_url = "http://localhost:8080/v1"
    settings.llm_timeout = 5.0
    settings.constitutional_model = "test-model"
    settings.cors_origins = ["http://localhost:3000"]
    settings.cors_allow_credentials = True
    settings.log_level = "DEBUG"
    settings.log_json = False
    settings.log_file = None

    # CRAG settings
    settings.crag_enabled = False
    settings.crag_enable_self_reflection = False
    settings.cag_enabled = False
    settings.cag_enable_self_reflection = False

    # Reranking settings
    settings.reranking_enabled = False
    settings.reranking_score_threshold = 0.3
    settings.reranking_top_n = 5

    # Mode settings
    settings.mode_evidence_temperature = 0.15
    settings.mode_evidence_top_p = 0.9
    settings.mode_evidence_repeat_penalty = 1.1
    settings.mode_evidence_num_predict = 1024
    settings.mode_assist_temperature = 0.4
    settings.mode_assist_top_p = 0.9
    settings.mode_assist_repeat_penalty = 1.1
    settings.mode_assist_num_predict = 1024

    return settings


@pytest.fixture
def mock_config_service(mock_config_settings):
    """Mock ConfigService with test defaults."""
    config = MagicMock()
    config.settings = mock_config_settings
    config.chromadb_path = "/tmp/test_chromadb"
    config.structured_output_effective_enabled = False
    config.critic_revise_effective_enabled = False
    return config


# ═══════════════════════════════════════════════════════════════════
# MOCK LLM SERVICE
# ═══════════════════════════════════════════════════════════════════


class MockLLMStats:
    """Mock LLM generation stats."""

    def __init__(self):
        self.tokens_generated = 42
        self.total_duration_ms = 100.0
        self.model_used = "test-model"
        self.tokens_per_second = 420.0


@pytest.fixture
def mock_llm_service():
    """Mock LLMService that returns canned responses without network calls."""
    service = AsyncMock()
    service.is_initialized = True
    service.initialize = AsyncMock()
    service.close = AsyncMock()
    service.health_check = AsyncMock(return_value=True)

    # Default streaming response
    async def mock_chat_stream(messages=None, config_override=None):
        yield "Detta är ett ", None
        yield "testsvar.", None
        yield None, MockLLMStats()

    service.chat_stream = mock_chat_stream
    return service


# ═══════════════════════════════════════════════════════════════════
# MOCK RETRIEVAL SERVICES
# ═══════════════════════════════════════════════════════════════════


class MockSearchResult:
    """Minimal SearchResult for testing."""

    def __init__(
        self,
        id: str = "doc_1",
        title: str = "Test Document",
        snippet: str = "Test content about Swedish law.",
        score: float = 0.85,
        source: str = "riksdag",
        doc_type: str = "proposition",
        date: str = "2024-01-01",
        retriever: str = "dense",
        tier: str = "primary",
    ):
        self.id = id
        self.title = title
        self.snippet = snippet
        self.score = score
        self.source = source
        self.doc_type = doc_type
        self.date = date
        self.retriever = retriever
        self.tier = tier


class MockRetrievalResult:
    """Mock retrieval result with metrics."""

    def __init__(self, results=None, intent="LEGAL_TEXT"):
        self.results = results or [
            MockSearchResult(id="doc_1", title="RF 2 kap.", score=0.92),
            MockSearchResult(id="doc_2", title="TF 2 kap.", score=0.85),
            MockSearchResult(id="doc_3", title="Prop 2023/24:1", score=0.78),
        ]
        self.success = True
        self.error = None
        self.intent = intent
        self.routing_used = "test_routing"
        self.metrics = MagicMock()
        self.metrics.strategy = "parallel_v1"
        self.metrics.top_score = 0.92 if self.results else 0.0


@pytest.fixture
def mock_search_results():
    """Standard set of mock search results."""
    return [
        MockSearchResult(
            id="sfs_2023_1",
            title="Regeringsformen 2 kap. 1 §",
            snippet="Var och en är gentemot det allmänna tillförsäkrad yttrandefrihet.",
            score=0.95,
            doc_type="sfs",
            source="riksdag",
        ),
        MockSearchResult(
            id="prop_2023_1",
            title="Proposition 2023/24:1",
            snippet="Regeringen föreslår att riksdagen antar följande lag.",
            score=0.82,
            doc_type="proposition",
            source="riksdag",
        ),
        MockSearchResult(
            id="sou_2023_1",
            title="SOU 2023:42",
            snippet="Utredningen har analyserat behovet av förändringar.",
            score=0.75,
            doc_type="sou",
            source="government",
        ),
    ]


@pytest.fixture
def mock_retrieval_service(mock_search_results):
    """Mock RetrievalService that returns canned results."""
    service = AsyncMock()
    service.is_initialized = True
    service.initialize = AsyncMock()
    service.close = AsyncMock()
    service.health_check = AsyncMock(return_value=True)
    service._chromadb_client = MagicMock()

    result = MockRetrievalResult(results=mock_search_results)
    service.search_with_epr = AsyncMock(return_value=result)
    service.search = AsyncMock(return_value=result)
    return service


# ═══════════════════════════════════════════════════════════════════
# MOCK OTHER SERVICES
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_query_processor():
    """Mock QueryProcessorService."""
    from app.services.query_processor_service import ResponseMode

    service = MagicMock()
    service.is_initialized = True
    service.initialize = AsyncMock()

    classification = MagicMock()
    classification.mode = ResponseMode.ASSIST
    classification.reason = "test classification"
    service.classify_query = MagicMock(return_value=classification)

    decontext = MagicMock()
    decontext.original_query = "test query"
    decontext.rewritten_query = "test query (decontextualized)"
    decontext.confidence = 0.9
    service.decontextualize_query = MagicMock(return_value=decontext)

    service.get_mode_config = MagicMock(return_value={"temperature": 0.15, "num_predict": 1024})
    return service


@pytest.fixture
def mock_guardrail_service():
    """Mock GuardrailService."""
    service = MagicMock()
    service.is_initialized = True
    service.initialize = AsyncMock()

    # Query safety check — default: safe
    service.check_query_safety = MagicMock(return_value=(True, None))

    # Response validation — default: no corrections
    validation_result = MagicMock()
    validation_result.corrections = []
    validation_result.corrected_text = ""
    validation_result.status = "unchanged"
    service.validate_response = MagicMock(return_value=validation_result)
    return service


@pytest.fixture
def mock_reranker():
    """Mock RerankingService."""
    service = AsyncMock()
    service.is_initialized = True
    service.initialize = AsyncMock()
    return service


@pytest.fixture
def mock_structured_output():
    """Mock StructuredOutputService."""
    service = MagicMock()
    service.is_initialized = True
    service.initialize = AsyncMock()
    return service


@pytest.fixture
def mock_critic_service():
    """Mock CriticService."""
    service = AsyncMock()
    service.is_initialized = True
    service.initialize = AsyncMock()
    return service


@pytest.fixture
def mock_grader_service():
    """Mock GraderService."""
    service = AsyncMock()
    service.is_initialized = True
    service.initialize = AsyncMock()
    return service


# ═══════════════════════════════════════════════════════════════════
# ORCHESTRATOR SERVICE (FULLY MOCKED)
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_orchestrator(
    mock_config_service,
    mock_llm_service,
    mock_query_processor,
    mock_guardrail_service,
    mock_retrieval_service,
    mock_reranker,
    mock_structured_output,
    mock_critic_service,
    mock_grader_service,
):
    """
    OrchestratorService with all dependencies mocked.
    Suitable for testing orchestrator logic without any external services.
    """
    from app.services.orchestrator_service import OrchestratorService

    orchestrator = OrchestratorService(
        config=mock_config_service,
        llm_service=mock_llm_service,
        query_processor=mock_query_processor,
        guardrail=mock_guardrail_service,
        retrieval=mock_retrieval_service,
        reranker=mock_reranker,
        structured_output=mock_structured_output,
        critic=mock_critic_service,
        grader=mock_grader_service,
    )
    orchestrator._initialized = True
    return orchestrator


# ═══════════════════════════════════════════════════════════════════
# FASTAPI TEST CLIENT
# ═══════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def async_client(
    mock_orchestrator,
    mock_retrieval_service,
) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient for testing FastAPI endpoints with all services mocked.
    Uses dependency_overrides to inject mocks.
    """
    from app.main import app
    from app.services.orchestrator_service import get_orchestrator_service
    from app.services.retrieval_service import get_retrieval_service
    from app.api.document_routes import get_retrieval_service_dependency

    # Override FastAPI dependencies
    app.dependency_overrides[get_orchestrator_service] = lambda: mock_orchestrator
    app.dependency_overrides[get_retrieval_service] = lambda: mock_retrieval_service
    app.dependency_overrides[get_retrieval_service_dependency] = lambda: mock_retrieval_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup overrides
    app.dependency_overrides.clear()
