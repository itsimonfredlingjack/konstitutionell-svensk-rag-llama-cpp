# AGENTS.md - Guide for AI Coding Agents

## Project Overview
Swedish RAG system: 538K+ ChromaDB docs (2M on USB), FastAPI backend (port 8900), React frontends (3000, 5175), Ollama (11434), LLM: ministral-3:14b.

## Build, Lint, Test Commands

### Python (Backend, Scrapers)
```bash
cd backend
pip install -r requirements.txt
ruff check backend/              # Lint
ruff check --fix backend/         # Auto-fix
ruff format backend/              # Format
pytest tests/test_file.py -v      # SINGLE TEST FILE
pytest tests/test_file.py::test_function -v  # SINGLE TEST
pytest -k "test_search" -v      # PATTERN MATCH
```

### TypeScript (Frontends)
```bash
cd apps/constitutional-gpt  # or -dashboard
npm install
npm run dev        # Dev server
npm run build      # Production
npm run lint       # ESLint
npm test -- src/test_file.test.ts  # SINGLE TEST
```

## Code Style Guidelines

### Python
**Imports** (standard → third-party → local):
```python
import json, logging
from pathlib import Path
from typing import Dict, Optional
import requests, chromadb
from utils.rate_limiter import RateLimiter
```

**Type Hints** (required):
```python
def fetch(url: str, timeout: int = 30) -> Optional[Dict]:
    """Fetches from URL."""
    ...
```

**Naming**: `snake_case` (functions/vars), `PascalCase` (classes), `UPPER_SNAKE_CASE` (constants), `_private` (methods).

**Error Handling**: Use structured logging, `logger.error(..., exc_info=True)`, raise custom exceptions from caught ones.

**Formatting**: Double quotes, line length 100, f-strings.

### TypeScript
**Components**: Function components with hooks only, use `import type` for type-only imports.

**Imports**: React/Next → External → Internal → Types.

**Styling**: Tailwind CSS with `cn()` utility.

## CRITICAL GUARDRAILS - Follow These ALWAYS

### 1. NEVER DELETE FILES without Permission
NEVER delete: `gemmis-os-ui`, ChromaDB data, backups, `/app/` (deprecated), docs, config.
ALWAYS: Ask first, check usage with `grep`, confirm user.

### 2. NEVER START SERVICES without Port Check
ALWAYS check ports first: `lsof -i :8900` (backend), `:3000` (gpt), `:5175` (dashboard), `:11434` (Ollama).
Check systemd: `systemctl --user status constitutional-ai-backend`.

### 3. ALWAYS READ CODE before Modifying
NEVER guess or change without context. ALWAYS read relevant files, use `grep` to find related code, check docs first.

### 4. ALWAYS CHECK ENDPOINTS before Claiming
NEVER claim missing without checking. ALWAYS: `grep -r "@router" backend/app/api/`, check `http://localhost:8900/docs`, test with `curl`.

## Configuration Files
- `backend/pyproject.toml` - Ruff, pytest, mypy (line length: 100)
- `.cursorrules` - CRITICAL Swedish/English guardrails (READ FIRST!)
- `CONTRIBUTING.md` - Detailed guidelines
- `docs/TESTING_GUIDE.md` - Testing framework
- `RAG_FIX_REPORT.md` - RAG bug fixes (critical)
- `BUILD_MODE_COMPLETE.md` - System status

## Testing Notes
Python: `tests/`, `backend/tests/`, single test: `python -m pytest tests/test_file.py::test_func -v`, pattern: `python -m pytest -k "test_search" -v`.
Frontend: Vitest in apps, single test: `npm test -- src/test.test.ts`.


## Service Management
```bash
# Backend (port 8900)
systemctl --user status constitutional-ai-backend
# Frontend GPT (port 3000)
systemctl --user status constitutional-gpt
# Frontend Dashboard (port 5175)
# Ollama (port 11434)
ollama ps
```

## Important Locations
- Backend API: `backend/app/api/constitutional_routes.py`
- Backend Entry: `backend/app/main.py`
- Frontend GPT Config: `apps/constitutional-gpt/src/config/env.ts` (port 8900)
- ChromaDB: `chromadb_data/` (15GB, 538,039 docs)
- Raw Docs: `data/documents_raw/` (USB backups - EMPTY, needs population)

## Common Mistakes to Avoid
1. Deleted files without asking
2. Started services without port check
3. Guessed code behavior (read first!)
4. Claimed endpoints missing without checking
5. Used wrong backend port (8900, NOT 8000)

## For Agentic AI Assistants
**READ `.cursorrules` FIRST** before any changes - contains critical Swedish/English guardrails and project-specific rules.
