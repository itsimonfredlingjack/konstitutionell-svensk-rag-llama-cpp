"""
Base Service - Abstract Base Class for All Services
Provides common interface and utilities for service implementations
"""

from abc import ABC, abstractmethod

from ..core.exceptions import ServiceNotInitializedError
from .config_service import ConfigService
from ..utils.logging import get_logger

logger = get_logger(__name__)


class BaseService(ABC):
    """
    Base class for all services.

    Provides:
    - Config access
    - Logging
    - Error handling pattern
    - Service lifecycle management (initialize, health_check, close)

    All services should inherit from this class.
    """

    def __init__(self, config: ConfigService):
        """
        Initialize base service.

        Args:
            config: ConfigService instance for configuration access
        """
        self.config = config
        self.logger = logger
        self._initialized: bool = False

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize service (load models, connect to DB, etc.).

        Should be called once before using the service.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Cleanup resources (close connections, unload models, etc.).

        Should be called when shutting down the service.
        """
        pass

    async def ensure_initialized(self) -> None:
        """
        Ensure service is initialized, raise exception if not.

        Raises:
            ServiceNotInitializedError: If service is not initialized
        """
        if not self._initialized:
            raise ServiceNotInitializedError(
                f"{self.__class__.__name__} is not initialized. " f"Call initialize() first."
            )

    def _mark_initialized(self) -> None:
        """
        Mark service as initialized.

        Called by subclasses after successful initialization.
        """
        self._initialized = True
        self.logger.info(f"{self.__class__.__name__} initialized")

    def _mark_uninitialized(self) -> None:
        """
        Mark service as uninitialized.

        Called by subclasses after cleanup.
        """
        self._initialized = False
        self.logger.info(f"{self.__class__.__name__} uninitialized")

    @property
    def is_initialized(self) -> bool:
        """
        Check if service is initialized.

        Returns:
            True if initialized, False otherwise
        """
        return self._initialized

    async def __aenter__(self) -> "BaseService":
        """
        Async context manager entry.

        Usage:
            async with service:
                await service.some_method()

        Automatically calls initialize() on entry.
        """
        if not self._initialized:
            await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Async context manager exit.

        Automatically calls close() on exit.
        """
        await self.close()
