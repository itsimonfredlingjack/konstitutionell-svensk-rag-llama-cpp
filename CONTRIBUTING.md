# Contributing to Constitutional AI

This document describes the code style and contribution guidelines for the Constitutional AI project.

## Project Structure

```
09_CONSTITUTIONAL-AI/
├── apps/                    # TypeScript/React applications
│   ├── constitutional-gpt/      # Main agentic RAG interface (Next.js 16)
│   └── constitutional-gpt-database/ # Database interface
├── scrapers/                # Python web scrapers (~100 files)
├── juridik-ai/              # Python legal AI pipelines
├── scripts/                 # Python utility scripts
├── indexers/                # ChromaDB/Qdrant indexing
└── data/                    # Document storage
```

## Language Guidelines

### Python (scrapers/, juridik-ai/, scripts/, indexers/)

#### Type Hints (Required)

All functions must have type hints for parameters and return values:

```python
# Good
def fetch_document(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    ...

# Bad - missing type hints
def fetch_document(url, timeout=30):
    ...
```

#### Docstrings

Use Swedish or English docstrings. Be consistent within a file:

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
    ...
```

#### Error Handling

Always use comprehensive try/except with specific exceptions:

```python
# Good
try:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
except requests.Timeout:
    logger.warning(f"Timeout för {url}")
    return None
except requests.HTTPError as e:
    logger.error(f"HTTP-fel för {url}: {e}")
    return None

# Bad - bare except
try:
    response = requests.get(url)
except:
    return None
```

#### Import Order

1. Standard library imports
2. Third-party imports
3. Local imports

```python
# Standard library
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Third-party
import requests
from bs4 import BeautifulSoup
import chromadb

# Local
from utils.rate_limiter import RateLimiter
from scrapers.base import BaseScraper
```

#### Naming Conventions

- **Functions/variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: `_leading_underscore`

### TypeScript/React (apps/)

#### Component Style

Use function components with hooks:

```typescript
// Good
export function SearchResults({ query, limit = 10 }: SearchResultsProps) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  
  useEffect(() => {
    // ...
  }, [query]);
  
  return <div>...</div>;
}

// Bad - class components
class SearchResults extends React.Component { ... }
```

#### Type Imports

Use `import type` for type-only imports:

```typescript
// Good
import type { SearchResult, QueryOptions } from '../types';
import { searchDocuments } from '../lib/api';

// Bad - mixing type and value imports unnecessarily
import { SearchResult, QueryOptions, searchDocuments } from '../lib/api';
```

#### Custom Hooks

Extract reusable logic into custom hooks with `use` prefix:

```typescript
// Good
export function useSystemMetrics() {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  // ...
  return { metrics, loading, error };
}
```

#### Import Order

1. React/Next.js imports
2. External library imports
3. Internal imports (lib/, components/, app/)
4. Type imports

```typescript
// React/Next
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';

// External
import { motion } from 'framer-motion';
import { Search, ChevronRight } from 'lucide-react';

// Internal
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

// Types
import type { SearchResult } from '@/types';
```

#### Styling

Use Tailwind CSS with `cn()` utility for conditional classes:

```typescript
import { cn } from '@/lib/utils';

<div className={cn(
  "p-4 rounded-lg",
  isActive && "bg-blue-500",
  isDisabled && "opacity-50 cursor-not-allowed"
)}>
```

## Code Quality Tools

### Pre-commit Hooks

Install pre-commit hooks before contributing:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run on all files (optional)
pre-commit run --all-files
```

### Python Linting (Ruff)

We use [Ruff](https://docs.astral.sh/ruff/) for Python linting and formatting:

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

### TypeScript Linting (ESLint)

Each app has its own ESLint configuration:

```bash
# In constitutional-gpt
cd apps/constitutional-gpt && npm run lint
```

## Commit Guidelines

### Commit Messages

Use conventional commit format:

```
<type>(<scope>): <description>

[optional body]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(scrapers): add Bolagsverket scraper
fix(indexers): handle empty PDF content
docs(readme): update installation instructions
refactor(juridik-ai): extract common parsing logic
```

## Testing

### Python Tests

```bash
cd juridik-ai
python -m pytest tests/ -v
```

### TypeScript Tests

```bash
cd apps/constitutional-gpt
npm test
```

## Pull Request Process

1. Create a feature branch: `git checkout -b feat/my-feature`
2. Make your changes
3. Ensure all linting passes: `pre-commit run --all-files`
4. Ensure tests pass
5. Commit with conventional commit message
6. Push and create PR

## Questions?

Check [CLAUDE.md](./CLAUDE.md) for project-specific context and architecture details.
