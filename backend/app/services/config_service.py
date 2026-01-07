"""
Config Service - Centralized Configuration for Constitutional AI
Wraps pydantic-settings with environment variable support
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path
from typing import Optional

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
    default_collections: list[str] = ["sfs_lagtext", "riksdag_documents_p1", "swedish_gov_docs"]

    # Embedding Model (KBLab Swedish BERT)
    embedding_model: str = "KBLab/sentence-bert-swedish-cased"
    expected_embedding_dim: int = 768

    # LLM Configuration (Constitutional AI)
    constitutional_model: str = "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
    constitutional_fallback: str = "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
    llm_timeout: float = 60.0

    # LLM Base URL (OpenAI-compatible llama-server)
    llm_base_url: str = "http://localhost:8080/v1"
    llama_server_base_url: str = "http://localhost:8080/v1"
    llama_server_enabled: bool = True
    llama_server_timeout: float = 120.0
    gguf_primary_model: str = "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
    gguf_context_window: int = 32768

    # Response Modes
    mode_evidence_temperature: float = 0.2
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

    # Parallel Search
    parallel_search_enabled: bool = True
    parallel_search_timeout: float = 5.0
    max_concurrent_queries: int = 3

    # Reranking (BGE)
    reranking_model: str = "BAAI/bge-reranker-v2-m3"
    reranking_enabled: bool = True
    reranking_top_k: int = 10

    # Jail Warden v2
    jail_warden_enabled: bool = True

    # Query Processing
    query_decontextualization_enabled: bool = True
    query_expansion_enabled: bool = True
    max_query_variants: int = 3

    # Adaptive Retrieval
    adaptive_retrieval_enabled: bool = True
    confidence_threshold_low: float = 0.4
    confidence_threshold_high: float = 0.7
    max_escalation_steps: int = 3

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
    critic_revise_enabled: bool = False  # Default False för safe rollout
    critic_max_revisions: int = 2
    critic_temperature: float = 0.1

    # Refusal Template
    evidence_refusal_template: str = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera. Om du vill kan du omformulera frågan eller ange vilka dokument/avsnitt du vill att jag ska söker i."


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
    def search_timeout(self) -> float:
        return self._settings.search_timeout

    @property
    def parallel_search_enabled(self) -> bool:
        return self._settings.parallel_search_enabled

    @property
    def max_concurrent_queries(self) -> int:
        return self._settings.max_concurrent_queries

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

        return mode_config_map.get(mode.lower(), mode_config_map["assist"])

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
