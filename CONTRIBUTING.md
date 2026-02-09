# Contributing to Constitutional AI

Kodstil och bidragsguide.

## Projektstruktur

```
09_CONSTITUTIONAL-AI/
├── apps/
│   └── constitutional-retardedantigravity/  # React + Vite + Three.js frontend
├── backend/                 # FastAPI backend (port 8900)
│   ├── app/
│   │   ├── api/             # API routes
│   │   ├── services/        # 30 service-moduler
│   │   ├── core/            # Error handlers, middleware, rate limiter
│   │   └── utils/           # Logging, metrics
│   └── tests/               # 16 testfiler
├── scrapers/                # Python web scrapers
│   ├── myndigheter/         # Myndighets-scrapers (40 filer)
│   ├── kommuner/            # Kommun-scrapers (4 filer)
│   └── media/               # Media-scrapers (8 filer)
├── indexers/                # ChromaDB-indexering (25+ scripts)
├── eval/                    # Utvärderingsverktyg
└── docs/                    # Dokumentation
```

## Python (backend/, scrapers/, indexers/)

### Verktyg

- **Linter/formatter:** Ruff (line-length 100, target py310)
- **Typecheck:** MyPy
- **Tester:** pytest + pytest-asyncio (asyncio_mode = "auto")
- **Config:** pyproject.toml

### Type hints (obligatoriskt)

```python
def fetch_document(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    ...
```

### Docstrings

Svenska eller engelska, var konsekvent inom en fil:

```python
def hämta_dokument(url: str) -> Dict[str, Any]:
    """Hämtar ett dokument från angiven URL.

    Args:
        url: URL till dokumentet

    Returns:
        Dict med dokumentdata

    Raises:
        requests.RequestException: Vid nätverksfel
    """
```

### Felhantering

Specifika exceptions, aldrig bare except:

```python
try:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
except requests.Timeout:
    logger.warning(f"Timeout för {url}")
    return None
except requests.HTTPError as e:
    logger.error(f"HTTP-fel för {url}: {e}")
    return None
```

### Import-ordning

1. Standardbibliotek
2. Tredjepartsbibliotek
3. Lokala imports

```python
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
import chromadb

from utils.rate_limiter import RateLimiter
from scrapers.base import BaseScraper
```

### Namngivning

- Funktioner/variabler: `snake_case`
- Klasser: `PascalCase`
- Konstanter: `UPPER_SNAKE_CASE`
- Privata metoder: `_leading_underscore`

## TypeScript/React (apps/constitutional-retardedantigravity/)

### Verktyg

- **Framework:** React 19 + Vite 7
- **Språk:** TypeScript 5.9 (strict mode)
- **Linter:** ESLint 9
- **Styling:** Tailwind CSS 4
- **State:** Zustand 5
- **3D:** Three.js via React Three Fiber + Drei

### Funktionella komponenter

```typescript
export function SearchResults({ query, limit = 10 }: SearchResultsProps) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // ...
  }, [query]);

  return <div>...</div>;
}
```

### Type imports

```typescript
import type { SearchResult, QueryOptions } from '../types';
import { searchDocuments } from '../lib/api';
```

### Custom hooks

```typescript
export function useSystemMetrics() {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  // ...
  return { metrics, loading, error };
}
```

### Import-ordning

1. React-imports
2. Externa bibliotek
3. Interna imports (`@/lib/`, `@/components/`)
4. Type imports

```typescript
import { useState, useEffect } from 'react';

import { motion } from 'framer-motion';
import { Search } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

import type { SearchResult } from '@/types';
```

### Styling

Tailwind CSS med `cn()` för conditional classes:

```typescript
import { cn } from '@/lib/utils';

<div className={cn(
  "p-4 rounded-lg",
  isActive && "bg-blue-500",
  isDisabled && "opacity-50 cursor-not-allowed"
)}>
```

## Kodkvalitet

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

### Lint

```bash
# Python
ruff check .
ruff check --fix .
ruff format .

# Frontend
cd apps/constitutional-retardedantigravity && npm run lint
```

## Commits

Conventional commits:

```
<type>(<scope>): <description>
```

Typer: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

```
feat(scrapers): add Bolagsverket scraper
fix(indexers): handle empty PDF content
docs(readme): update installation instructions
refactor(backend): extract common parsing logic
```

## Tester

```bash
cd backend
pytest tests/ -v
pytest -m "not integration and not slow"
```

## Pull requests

1. Skapa feature branch: `git checkout -b feat/my-feature`
2. Gör ändringar
3. Kör lint: `pre-commit run --all-files`
4. Kör tester: `pytest tests/ -v -m "not integration"`
5. Committa med conventional commit
6. Pusha och skapa PR
