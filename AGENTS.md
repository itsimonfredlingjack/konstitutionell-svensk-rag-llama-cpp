# Repository Guidelines

## Project structure & module organization
This repository combines a FastAPI backend, a React frontend, and data
pipelines for scraping, indexing, and evaluation.

- `backend/`: API and RAG orchestration (`backend/app/` for runtime code,
  `backend/tests/` for backend-focused tests).
- `apps/constitutional-retardedantigravity/`: React 19 + TypeScript frontend.
- `scrapers/`: Source collection scripts (`myndigheter/`, `kommuner/`,
  `media/`).
- `indexers/`: ChromaDB indexing and ingestion utilities.
- `tests/`: Root-level integration and contract-style tests.
- `docs/`: Architecture, operations, and evaluation documentation.

## Build, test, and development commands
Use these commands from the repository root unless noted otherwise.

- Backend dev server: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8900`
- Frontend dev server: `cd apps/constitutional-retardedantigravity && npm install && npm run dev`
- Frontend production build: `cd apps/constitutional-retardedantigravity && npm run build`
- Python lint/format: `ruff check .`, `ruff check --fix .`, `ruff format .`
- Backend tests (fast path): `cd backend && pytest tests/ -v -m "not integration and not ollama and not slow"`
- Full local stack: `docker compose up`

## Coding style & naming conventions
Follow the configured tooling instead of ad hoc formatting.

- Python: Ruff + MyPy, line length 100, spaces for indentation, double quotes.
- TypeScript: strict mode enabled, ESLint 9 (`npm run lint`).
- Naming: `snake_case` for Python functions and variables, `PascalCase` for
  classes and React components, `UPPER_SNAKE_CASE` for constants.
- Keep modules focused. Place new backend business logic in
  `backend/app/services/` and API route wiring in `backend/app/api/`.

## Testing guidelines
Pytest is the canonical test runner for Python code.

- Test file naming: `test_*.py` or `*_test.py`.
- Mark long-running or environment-dependent tests with existing markers
  (`integration`, `slow`, `ollama`).
- Add unit tests for new logic and at least one integration-level test when
  behavior crosses service boundaries.

## Commit & pull request guidelines
History follows Conventional Commits, for example:
`feat(eval): add chunk quality analysis` and
`fix(frontend): update canonical URLs`.

- Format commits as `<type>(<scope>): <description>`.
- Before opening a PR, run backend lint/tests and frontend lint/build locally.
- PRs should include: what changed, why it changed, impacted paths, and any UI
  screenshot for frontend-visible updates.
