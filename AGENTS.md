# AGENTS.md - Guide for AI Coding Agents

## Project Overview

Swedish government document RAG system with 538K+ ChromaDB documents (2M on USB).
- **Backend**: FastAPI (port 8900) in `backend/app/` - systemd: `constitutional-ai-backend`
- **Frontend**: React/Vite apps in `apps/constitutional-gpt` (port 3000) and `apps/constitutional-dashboard` (port 5175)
- **Vector DB**: ChromaDB in `chromadb_data/` (15GB, 538,039 docs)
- **LLM**: Ollama (port 11434) with `ministral-3:14b` primary

## Build, Lint, Test Commands

### Python (Backend, Scrapers)
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Linting with Ruff
ruff check backend/              # Check for issues
ruff check --fix backend/        # Auto-fix issues
ruff format backend/             # Format code

# Type checking
mypy backend/ --ignore-missing-imports

# Run tests - SINGLE TEST FILE
pytest tests/test_file.py -v

# Run tests - SINGLE TEST FUNCTION
pytest tests/test_file.py::test_function_name -v

# Run tests - PATTERN MATCHING
pytest -k "test_search" -v

# Run all tests
pytest tests/ -v

# Frontend test (Vitest)
cd apps/constitutional-gpt
npm test -- src/test_file.test.ts
```

### TypeScript (Frontend Apps)
```bash
cd apps/constitutional-gpt  # or constitutional-dashboard
npm install
npm run dev        # Dev server
npm run build      # Production build
npm run lint       # ESLint
npm run preview    # Preview production build
```

## Code Style Guidelines

### Python

**Imports** (Ruff-enforced order):
```python
# Standard library
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

# Third-party
import requests
from bs4 import BeautifulSoup
import chromadb

# Local
from backend.app.utils.rate_limiter import RateLimiter
from backend.app.scrapers.base import BaseScraper
```

**Type Hints** (Required for all functions):
```python
def fetch_document(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """Fetches a document from given URL."""
    ...
```

**Naming Conventions**:
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

**Error Handling** (Always use structured logging):
```python
try:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()
except requests.Timeout:
    logger.warning(f"Timeout for {url}")
    return None
except requests.HTTPError as e:
    logger.error(f"HTTP error for {url}: {e}", exc_info=True)
    raise RetrievalError(f"Failed to fetch {url}") from e
```

**Formatting** (Ruff): Double quotes, line length 100, f-strings for formatting

### TypeScript/React

**Components** (Function components with hooks only):
```typescript
export function SearchResults({ query, limit = 10 }: SearchResultsProps) {
  const [results, setResults] = useState<SearchResult[]>([]);
  return <div>...</div>;
}
```

**Imports**:
```typescript
// React/Next
import { useState, useEffect } from 'react';

// External
import { motion } from 'framer-motion';

// Internal
import { cn } from '@/lib/utils';

// Types (type-only imports)
import type { SearchResult } from '@/types';
```

**Styling**: Tailwind CSS with `cn()` utility for conditional classes

## CRITICAL GUARDRAILS - Follow These ALWAYS

### 1. NEVER DELETE FILES without Explicit Permission
**NEVER delete**:
- `gemmis-os-ui` or other projects
- ChromaDB data (`chromadb_data/`)
- Backups
- Documentation or config files
- `/app/` (deprecated duplicate backend)

**ALWAYS**:
- Ask: "Should I delete X?"
- Check if file is used with `grep`
- Confirm with user before destructive operations

### 2. NEVER START SERVICES without Port Check
**Check ports first**:
```bash
lsof -i :8900   # Backend
lsof -i :3000   # Frontend GPT
lsof -i :5175   # Frontend Dashboard
lsof -i :11434  # Ollama
```

**Check systemd services**:
```bash
systemctl --user status constitutional-ai-backend
```

### 3. ALWAYS READ CODE before Modifying
**NEVER**:
- Guess what code does
- Modify without understanding context
- Create features without checking if they exist

**ALWAYS**:
- Read relevant files first
- Use `grep` or `codebase_search` to find related code
- Check documentation before implementation

### 4. ALWAYS CHECK ENDPOINTS before Claiming
**NEVER**:
- Claim endpoint doesn't exist without checking
- Create duplicate endpoints

**ALWAYS**:
```bash
# Check routes
grep -r "@router\|@app" backend/app/api/

# Check OpenAPI
curl http://localhost:8900/docs

# Test endpoint
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question":"test","mode":"evidence"}'
```

## Configuration Files

- `backend/pyproject.toml` - Ruff, pytest, mypy settings (line length: 100)
- `backend/.pre-commit-config.yaml` - Pre-commit hooks (ruff, ruff-format)
- `.cursorrules` - Additional project rules (Swedish/English mix, CRITICAL guardrails)
- `CONTRIBUTING.md` - Detailed contribution guidelines

## Testing Notes

- Python tests in `backend/tests/` and `juridik-ai/tests/`
- Frontend tests in `apps/constitutional-gpt/` (Vitest)
- **SINGLE TEST**: `pytest backend/tests/test_file.py::test_function -v`
- **PATTERN**: `pytest -k "test_search" -v`
- Test coverage goal: 75%+ (currently ~15-20%)

## Service Management

```bash
# Backend (constitutional-ai-backend - port 8900)
systemctl --user status constitutional-ai-backend
journalctl --user -u constitutional-ai-backend -f

# Frontends
systemctl --user status constitutional-gpt      # port 3000
systemctl --user status constitutional-dashboard # port 5175

# Ollama
ollama ps
ollama list
```

## Important Files and Locations

- **Backend API**: `backend/app/api/constitutional_routes.py` - Constitutional routes
- **Backend Entry**: `backend/app/main.py` - FastAPI app
- **Frontend GPT Config**: `apps/constitutional-gpt/src/config/env.ts` - API: http://localhost:8900
- **Frontend Dashboard**: `apps/constitutional-dashboard/src/` - Port 5175
- **ChromaDB**: `chromadb_data/` - 15GB, 538,039 embedded documents
- **Raw Documents**: `data/documents_raw/` - USB stick backups (EMPTY - needs population)

## Common Mistakes to Avoid

1. **Deleted files without asking** - ALWAYS get permission first
2. **Started services without port check** - ALWAYS check `lsof` first
3. **Guessed code behavior** - ALWAYS read code before modifying
4. **Claimed endpoints missing** - ALWAYS check `/docs` or grep routes first
5. **Used wrong backend port** - Port is 8900, NOT 8000

## References

- `.cursorrules` - CRITICAL guardrails in Swedish/English (READ THIS FIRST)
- `CONTRIBUTING.md` - Detailed contribution guidelines
- `docs/TESTING_GUIDE.md` - Testing framework guide
- `RAG_FIX_REPORT.md` - RAG system bug fixes (critical read)
- `BUILD_MODE_COMPLETE.md` - Build mode completion report

**For agentic AI assistants: Read `.cursorrules` FIRST before any changes!**
