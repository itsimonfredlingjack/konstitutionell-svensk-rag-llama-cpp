"""
Pytest configuration for backend tests.

Adds parent directory to Python path so tests can import `app` package.
"""

import os
import socket
import sys
from pathlib import Path

import pytest

# Add parent directory (backend/) to Python path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


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
    """Compatibility helper for existing tests.

    Returns True only when Ollama tests are enabled AND the service is reachable.
    """
    return _run_ollama_tests() and _port_open(host, port)


@pytest.fixture(scope="session")
def ollama_available() -> bool:
    """Fixture that returns True if Ollama is enabled and reachable."""
    return is_ollama_available()
