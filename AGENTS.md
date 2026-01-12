# AGENTS.md - Guide for AI Coding Agents

## Project Overview
Swedish RAG system: 538K+ ChromaDB docs (2M on USB), FastAPI backend (port 8900), React frontends (3000, 3001, 5175), Ollama (11434), LLM: ministral-3:14b.

## Build, Lint, Test Commands

### Python (Backend, Scrapers)
```bash
cd backend
pip install -r requirements.txt
ruff check .              # Lint
ruff check --fix .         # Auto-fix
ruff format .              # Format
pytest tests/ -v           # ALL TESTS
pytest tests/test_file.py -v      # SINGLE TEST FILE
pytest tests/test_file.py::test_function -v  # SINGLE TEST FUNCTION
pytest -k "test_search" -v        # PATTERN MATCH
pytest -m "unit" -v               # MARKER MATCH
```

### TypeScript (Frontends)
```bash
cd apps/constitutional-retardedantigravity  # PRIMARY FRONTEND
npm install
npm run dev        # Dev server (port 3001)
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

**Imports**: React → External → Internal → Types.

**Styling**: Tailwind CSS with `cn()` utility.

## CRITICAL GUARDRAILS - Follow These ALWAYS

### 1. READ .cursorrules FIRST
Contains critical Swedish/English guardrails and project-specific rules. **ALWAYS READ BEFORE ANY CHANGES**.

### 2. NEVER DELETE FILES without Permission
NEVER delete: `gemmis-os-ui`, ChromaDB data, backups, `/app/` (deprecated), docs, config.
ALWAYS: Ask first, check usage with `grep`, confirm user.

### 3. NEVER START SERVICES without Port Check
ALWAYS check ports first: `lsof -i :8900` (backend), `:3001` (main frontend), `:3000` (gpt), `:5175` (dashboard), `:11434` (Ollama).
Check systemd: `systemctl --user status constitutional-ai-backend`.

### 4. ALWAYS READ CODE before Modifying
NEVER guess or change without context. ALWAYS read relevant files, use `grep` to find related code, check docs first.

### 5. ALWAYS CHECK ENDPOINTS before Claiming
NEVER claim missing without checking. ALWAYS: `grep -r "@router" backend/app/api/`, check `http://localhost:8900/docs`, test with `curl`.

### 6. FRONTEND RULES (CRITICAL)
**THE ONLY CORRECT FRONTEND**: `/apps/constitutional-retardedantigravity/` (React + Vite + TypeScript, port 3001).
**NEVER**: Create new frontend apps, use Streamlit for frontend, touch `/frontend/` folder, push changes without verifying.
**ALWAYS**: Read `FRONTEND_README.md` first, use the existing app in `/apps/constitutional-retardedantigravity/`.

## Configuration Files
- `backend/pyproject.toml` - Ruff, pytest, mypy (line length: 100)
- `.cursorrules` - CRITICAL Swedish/English guardrails (READ FIRST!)
- `CONTRIBUTING.md` - Detailed guidelines
- `docs/TESTING_GUIDE.md` - Testing framework
- `RAG_FIX_REPORT.md` - RAG bug fixes (critical)
- `FRONTEND_README.md` - Frontend guardrails (READ BEFORE FRONTEND WORK!)

## Testing Notes
Python: `tests/`, `backend/tests/`, single test: `pytest tests/test_file.py::test_func -v`, pattern: `pytest -k "test_search" -v`, markers: `pytest -m "unit" -v`.
Frontend: Vitest in apps, single test: `npm test -- src/test.test.ts`.

## Service Management
```bash
# Backend (port 8900)
systemctl --user status constitutional-ai-backend
# Frontend (port 3001) - PRIMARY
cd apps/constitutional-retardedantigravity && npm run dev
# Ollama (port 11434)
ollama ps
```

## Important Locations
- Backend API: `backend/app/api/constitutional_routes.py`
- Backend Entry: `backend/app/main.py`
- Primary Frontend: `apps/constitutional-retardedantigravity/` (React + Vite, port 3001)
- Secondary Frontends: `apps/constitutional-gpt/` (Next.js, port 3000), `apps/constitutional-dashboard/` (Vite, port 5175)
- ChromaDB: `chromadb_data/` (15GB, 538,039 docs)
- Raw Docs: `data/documents_raw/` (USB backups - EMPTY, needs population)

## Common Mistakes to Avoid
1. Deleted files without asking
2. Started services without port check
3. Guessed code behavior (read first!)
4. Claimed endpoints missing without checking
5. Used wrong backend port (8900, NOT 8000)
6. Created new frontend app instead of using `/apps/constitutional-retardedantigravity/`
7. Used Streamlit for frontend (wrong!)

## For Agentic AI Assistants
**READ `.cursorrules` FIRST** before any changes - contains critical Swedish/English guardrails and project-specific rules.
**READ `FRONTEND_README.md`** before any frontend work - contains critical frontend guardrails.
