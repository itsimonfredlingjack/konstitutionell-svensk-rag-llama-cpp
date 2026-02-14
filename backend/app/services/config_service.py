"""
Config Service - Centralized Configuration for Constitutional AI
Wraps pydantic-settings with environment variable support
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ConfigSettings(BaseSettings):
    """Pydantic settings for configuration"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CONST_",  # All env vars start with CONST_
        extra="ignore",  # Ignore extra env vars
    )

    # Application
    app_name: str = "Constitutional AI"
    app_version: str = "2.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # ChromaDB Configuration
    chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
    pdf_cache_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/pdf_cache"

    # Collections
    default_collections: list[str] = [
        "sfs_lagtext",
        "riksdag_documents_p1",
        "swedish_gov_docs",
        "diva_research",
        "procedural_guides",
    ]

    # Embedding Model (Jina v3, 1024 dim, asymmetric encoding)
    # TODO(re-index): ALL ChromaDB collections must be re-indexed with Jina v3
    # embed_document() before queries work. Old _bge_m3_1024 collections are
    # incompatible — different vector space despite same dimensions.
    embedding_model: str = "jinaai/jina-embeddings-v3"
    expected_embedding_dim: int = 1024
    embedding_collection_suffix: str = "_jina_v3_1024"

    # LLM Configuration (Constitutional AI)
    constitutional_model: str = "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"
    # Intentionally same as primary — no separate fallback model downloaded
    constitutional_fallback: str = "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"
    llm_timeout: float = 60.0

    # LLM Base URL (OpenAI-compatible llama-server)
    llm_base_url: str = "http://localhost:8080/v1"
    llama_server_base_url: str = "http://localhost:8080/v1"
    llama_server_enabled: bool = True
    llama_server_timeout: float = 120.0
    gguf_primary_model: str = "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"
    gguf_context_window: int = 8192

    # Response Modes
    mode_evidence_temperature: float = 0.15
    mode_evidence_top_p: float = 0.9
    mode_evidence_repeat_penalty: float = 1.1
    mode_evidence_num_predict: int = 1024

    mode_assist_temperature: float = 0.4
    mode_assist_top_p: float = 0.9
    mode_assist_repeat_penalty: float = 1.1
    mode_assist_num_predict: int = 1024

    mode_chat_temperature: float = 0.7
    mode_chat_top_p: float = 0.9
    mode_chat_repeat_penalty: float = 1.1
    mode_chat_num_predict: int = 512

    # Search Configuration
    default_search_limit: int = 10
    max_search_limit: int = 100
    search_timeout: float = 5.0

    # RAG Similarity Threshold (replaces RAG_SIMILARITY_THRESHOLD env var)
    score_threshold: float = 0.35

    # Per-collection retrieval timeouts (seconds)
    retrieval_timeout_default: float = 5.0
    retrieval_timeout_sfs: float = 3.0
    retrieval_timeout_diva: float = 8.0

    # Parallel Search
    parallel_search_enabled: bool = True
    parallel_search_timeout: float = 5.0
    max_concurrent_queries: int = 3

    # Reranking (Jina)
    reranking_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    reranking_enabled: bool = True
    reranking_top_k: int = 10
    reranking_score_threshold: float = 0.1  # Filter docs below this reranker score
    reranking_top_n: int = 5  # Max docs to pass to LLM after reranking

    # Jail Warden v2
    jail_warden_enabled: bool = True

    # Query Processing
    query_decontextualization_enabled: bool = True
    query_expansion_enabled: bool = True
    query_expansion_count: int = 3
    query_expansion_use_grammar: bool = True
    max_query_variants: int = 3

    # Adaptive Retrieval
    adaptive_retrieval_enabled: bool = True
    confidence_threshold_low: float = 0.4
    confidence_threshold_high: float = 0.7
    max_escalation_steps: int = 3

    # Hybrid Search & RRF Fusion
    # BM25 weight in RRF: 1.0 = equal weight, 1.2 = slightly favor exact legal terms
    # Higher values prioritize exact SFS matches over semantic similarity
    rrf_bm25_weight: float = 1.2

    # RRF k constant: lower = top results dominate, higher = flatter distribution
    # k=60 is the original paper default, k=45 balances legal precision and recall
    rrf_k: float = 45.0

    # EPR hybrid search: use RAG-Fusion multi-query in EPR routing
    epr_use_rag_fusion: bool = True
    epr_fusion_num_queries: int = 3

    # BM25 hybrid search — disabled by default to reduce RAM (~3-4GB index)
    bm25_enabled: bool = False
    bm25_index_path: str = ""  # Override FTS5 DB path; empty = default

    # Cutover guardrails (fail-closed once migration is verified)
    cutover_enforce_jina_collections: bool = False
    cutover_allowed_fallback_collections: list[str] = []

    # Benchmark DoD gates
    benchmark_max_pipeline_ms_avg: float = 15000.0
    benchmark_max_pipeline_ms_p95: float = 25000.0
    benchmark_min_live_success_rate: float = 0.95
    benchmark_min_dense_hits_avg: float = 1.0
    benchmark_min_bm25_hits_avg: float = 1.0
    benchmark_min_crag_yes_rate_top5: float = 0.20

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.86.32:3000",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    cors_allow_credentials: bool = True

    # Logging
    log_level: str = "INFO"
    log_json: bool = False
    log_file: Optional[str] = None

    # Mock Data (for local development only)
    use_mock_data: bool = False

    # Structured Output & Critic→Revise Loop (Constitutional AI)
    structured_output_enabled: bool = True
    critic_revise_enabled: bool = True  # Enabled for answer quality improvement
    critic_max_revisions: int = 1  # Single revision pass for quality/latency balance
    critic_temperature: float = 0.1

    # Refusal Template
    evidence_refusal_template: str = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera. Om du vill kan du omformulera frågan eller ange vilka dokument/avsnitt du vill att jag ska söker i."

    # CRAG (Corrective RAG) Configuration
    crag_enabled: bool = True  # Enabled - filters irrelevant docs before LLM generation
    crag_grade_threshold: float = 0.15  # Relevance threshold (lowered for better edge-case recall)
    crag_max_rewrite_attempts: int = 2  # Max query rewrite attempts if no relevant docs
    crag_grader_model: str = (
        "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"  # Same as primary — single model setup
    )
    crag_enable_self_reflection: bool = False  # Chain of Thought before answering
    crag_max_concurrent_grading: int = 5  # Max parallel document grading
    crag_grade_timeout: float = 10.0  # Timeout per document grading in seconds


class ConfigService:
    """
    Centralized configuration service.

    Provides:
    - Singleton pattern (one instance per app)
    - Environment variable support
    - Configuration validation
    """

    _instance: Optional["ConfigService"] = None

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize configuration from environment"""
        self._settings: ConfigSettings = ConfigSettings()
        self._config: ConfigSettings = self._settings
        self._validate_paths()
        logger.info(
            f"ConfigService initialized: {self._settings.app_name} v{self._settings.app_version}"
        )

    def _validate_paths(self) -> None:
        """Validate that configured paths exist or can be created"""
        try:
            # Validate ChromaDB path
            chromadb_path = Path(self._settings.chromadb_path)
            if not chromadb_path.exists():
                logger.warning(f"ChromaDB path does not exist: {self._settings.chromadb_path}")

            # Validate PDF cache path
            pdf_cache_path = Path(self._settings.pdf_cache_path)
            if not pdf_cache_path.exists():
                logger.warning(f"PDF cache path does not exist: {self._settings.pdf_cache_path}")
        except Exception as e:
            logger.error(f"Path validation failed: {e}")

    @property
    def settings(self) -> ConfigSettings:
        """Access to raw Pydantic settings"""
        return self._settings

    # Convenience accessors for common settings

    @property
    def app_name(self) -> str:
        return self._settings.app_name

    @property
    def app_version(self) -> str:
        return self._settings.app_version

    @property
    def debug(self) -> bool:
        return self._settings.debug

    @property
    def host(self) -> str:
        return self._settings.host

    @property
    def port(self) -> int:
        return self._settings.port

    @property
    def chromadb_path(self) -> str:
        return self._settings.chromadb_path

    @property
    def pdf_cache_path(self) -> str:
        return self._settings.pdf_cache_path

    @property
    def constitutional_model(self) -> str:
        return self._settings.constitutional_model

    @property
    def constitutional_fallback(self) -> str:
        return self._settings.constitutional_fallback

    @property
    def llm_timeout(self) -> float:
        return self._settings.llm_timeout

    @property
    def llm_base_url(self) -> str:
        """Get the base URL for the OpenAI-compatible llama-server"""
        return self._settings.llm_base_url or self._settings.llama_server_base_url

    @property
    def llama_server_base_url(self) -> str:
        """Deprecated: use llm_base_url instead"""
        return self.llm_base_url

    @property
    def llama_server_enabled(self) -> bool:
        """Check if llama-server (RAG-optimized Ollama) is enabled"""
        return self._settings.llama_server_enabled

    @property
    def llama_server_timeout(self) -> float:
        """Get the timeout for llama-server requests"""
        return self._settings.llama_server_timeout

    @property
    def gguf_primary_model(self) -> str:
        """Get the primary GGUF model name"""
        return self._settings.gguf_primary_model

    @property
    def gguf_context_window(self) -> int:
        """Get the context window size for GGUF models"""
        return self._settings.gguf_context_window

    @property
    def embedding_model(self) -> str:
        return self._settings.embedding_model

    @property
    def expected_embedding_dim(self) -> int:
        return self._settings.expected_embedding_dim

    @property
    def reranking_model(self) -> str:
        return self._settings.reranking_model

    @property
    def default_collections(self) -> list[str]:
        return self._settings.default_collections

    @property
    def effective_default_collections(self) -> list[str]:
        """Return the default collections adjusted for embedding dimension changes."""
        base = self._settings.default_collections
        suffix = self._settings.embedding_collection_suffix

        if self._settings.expected_embedding_dim == 1024 and suffix:
            return [f"{name}{suffix}" for name in base]

        return base

    @property
    def search_timeout(self) -> float:
        return self._settings.search_timeout

    @property
    def parallel_search_enabled(self) -> bool:
        return self._settings.parallel_search_enabled

    @property
    def max_concurrent_queries(self) -> int:
        return self._settings.max_concurrent_queries

    @property
    def query_expansion_enabled(self) -> bool:
        return self._settings.query_expansion_enabled

    @property
    def query_expansion_count(self) -> int:
        return self._settings.query_expansion_count

    @property
    def query_expansion_use_grammar(self) -> bool:
        return self._settings.query_expansion_use_grammar

    @property
    def rrf_bm25_weight(self) -> float:
        return self._settings.rrf_bm25_weight

    @property
    def rrf_k(self) -> float:
        return self._settings.rrf_k

    @property
    def bm25_enabled(self) -> bool:
        return self._settings.bm25_enabled

    @property
    def bm25_index_path(self) -> str:
        return self._settings.bm25_index_path

    @property
    def score_threshold(self) -> float:
        return self._settings.score_threshold

    @property
    def cutover_enforce_jina_collections(self) -> bool:
        return self._settings.cutover_enforce_jina_collections

    @property
    def cutover_allowed_fallback_collections(self) -> list[str]:
        return self._settings.cutover_allowed_fallback_collections

    @property
    def retrieval_timeout_default(self) -> float:
        return self._settings.retrieval_timeout_default

    @property
    def retrieval_timeout_sfs(self) -> float:
        return self._settings.retrieval_timeout_sfs

    @property
    def retrieval_timeout_diva(self) -> float:
        return self._settings.retrieval_timeout_diva

    def get_collection_timeout(self, collection_name: str) -> float:
        """Get timeout for a specific collection based on its name."""
        if "sfs" in collection_name:
            return self._settings.retrieval_timeout_sfs
        elif "diva" in collection_name:
            return self._settings.retrieval_timeout_diva
        return self._settings.retrieval_timeout_default

    def get_mode_config(self, mode: str) -> dict:
        """
        Get model configuration for a specific response mode.

        Args:
            mode: Response mode (evidence, assist, chat)

        Returns:
            Dictionary with model configuration (temperature, top_p, etc.)
        """
        mode_config_map = {
            "evidence": {
                "temperature": self._settings.mode_evidence_temperature,
                "top_p": self._settings.mode_evidence_top_p,
                "repeat_penalty": self._settings.mode_evidence_repeat_penalty,
                "num_predict": self._settings.mode_evidence_num_predict,
            },
            "assist": {
                "temperature": self._settings.mode_assist_temperature,
                "top_p": self._settings.mode_assist_top_p,
                "repeat_penalty": self._settings.mode_assist_repeat_penalty,
                "num_predict": self._settings.mode_assist_num_predict,
            },
            "chat": {
                "temperature": self._settings.mode_chat_temperature,
                "top_p": self._settings.mode_chat_top_p,
                "repeat_penalty": self._settings.mode_chat_repeat_penalty,
                "num_predict": self._settings.mode_chat_num_predict,
            },
        }

        config = mode_config_map.get(mode.lower(), mode_config_map["assist"])

        # DETERMINISTIC_EVAL mode: force temperature=0, top_p=1 for consistent output
        if os.environ.get("DETERMINISTIC_EVAL", "").lower() == "true":
            config["temperature"] = 0.0
            config["top_p"] = 1.0

        return config

    @property
    def structured_output_effective_enabled(self) -> bool:
        """
        Consolidate all conditions for structured output enablement.

        Returns:
            True if structured output should be used, False otherwise
        """
        return (
            self._settings.structured_output_enabled
            and not self._settings.debug  # Disable in debug mode if needed
        )

    @property
    def critic_revise_effective_enabled(self) -> bool:
        """
        Consolidate all conditions for critic enablement.

        Returns:
            True if critic→revise loop should be used, False otherwise
        """
        return (
            self._settings.critic_revise_enabled
            and self._settings.structured_output_enabled  # Depends on structured output
        )

    def reload(self) -> None:
        """Reload configuration from environment"""
        self._settings = ConfigSettings()
        self._validate_paths()
        logger.info("Configuration reloaded")


@lru_cache()
def get_config_service() -> ConfigService:
    """
    Get singleton ConfigService instance.

    Returns:
        Cached ConfigService instance
    """
    return ConfigService()


# Global instance for backward compatibility
config_service = get_config_service()
