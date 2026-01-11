"""Repo-level pytest configuration.

Policy:
- Unit tests are the default fast/safe base.
- Anything marked `integration` / `ollama` / `chromadb` / `live_llm` is opt-in via env vars.

This keeps `pytest -m "not integration"` fast and prevents accidental service usage.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def pytest_configure(config):
    # Ensure backend imports (`import app...`) work from repo-root test runs.
    repo_root = Path(__file__).resolve().parent
    backend_root = repo_root / "backend"
    if backend_root.exists() and str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    # Declare markers to avoid PytestUnknownMarkWarning.
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (requires real services)"
    )
    config.addinivalue_line("markers", "unit: marks tests as unit tests (uses mocks)")
    config.addinivalue_line("markers", "slow: marks tests as slow (skip by default)")
    config.addinivalue_line("markers", "ollama: requires a running Ollama service (opt-in)")
    config.addinivalue_line("markers", "chromadb: requires a running ChromaDB service (opt-in)")
    config.addinivalue_line("markers", "live_llm: requires a live LLM endpoint (opt-in)")


def pytest_runtest_setup(item):
    """Default-safe: skip external-service tests unless explicitly enabled."""
    if "ollama" in item.keywords and not _env_truthy("RUN_OLLAMA"):
        pytest.skip("Ollama tests are opt-in (set RUN_OLLAMA=1)")
    if "chromadb" in item.keywords and not _env_truthy("RUN_CHROMADB"):
        pytest.skip("ChromaDB tests are opt-in (set RUN_CHROMADB=1)")
    if "live_llm" in item.keywords and not _env_truthy("RUN_LIVE_LLM"):
        pytest.skip("Live LLM tests are opt-in (set RUN_LIVE_LLM=1)")
    if "integration" in item.keywords and not _env_truthy("RUN_INTEGRATION"):
        pytest.skip("Integration tests are opt-in (set RUN_INTEGRATION=1)")
