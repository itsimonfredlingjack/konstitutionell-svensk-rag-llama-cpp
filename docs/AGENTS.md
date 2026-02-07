# Constitutional AI - Development Guide

## Build/Test Commands
```bash
# Frontend (React/Next.js)
npm run dev        # Development server
npm run build      # Production build  
npm run lint       # ESLint validation

# Python Testing
cd backend && python -m pytest tests/ -v

# System Commands
constitutional status                    # System status
curl http://localhost:8000/api/health   # Backend health check
```

## Code Style Guidelines

### TypeScript/JavaScript
- **Strict TypeScript**: All projects use strict mode, noUnusedLocals, noUnusedParameters
- **Imports**: ES6 imports only, use `@/` path aliases in Next.js, separate type imports when needed
- **Components**: Functional components with TypeScript interfaces, PascalCase for component names
- **Styling**: Tailwind CSS exclusively, use `clsx` for conditional classes
- **ESLint**: Modern flat config with typescript-eslint, react-hooks, react-refresh rules

### Python
- **CLI Framework**: Rich terminal UI with Typer for all command-line interfaces
- **Testing**: Comprehensive pytest suites, especially for Swedish document processing
- **Document Processing**: Specialized pipelines for Swedish government documents (SFS, propositioner, etc.)
- **AI Integration**: llama-server (llama.cpp) local models with Swedish optimization (KBLab embeddings)

### Architecture Patterns
- **Agentic RAG**: Direct RAG pattern with two-model architecture:
  - **Gemma 3 12B (BRAIN)**: Faktasvar, RAG, juridisk analys
  - **GPT-SW3 6.7B (VOICE)**: Chat, style pass, naturlig svenska
- **Response Modes**: CHAT (GPT-SW3 only), ASSIST (Gemma → GPT-SW3), EVIDENCE (Gemma only)
- **Structured Outputs**: OpenAI-compatible JSON mode via llama-server med JSON Schema
- **Swedish Processing**: Rate limiting for government APIs, Swedish text processing, ChromaDB vector operations
- **Error Handling**: Graceful degradation for document parsing, comprehensive logging for scraping operations
- **State Management**: React hooks for frontend, SQLite for scraper state tracking

### Naming Conventions
- **Files**: kebab-case for directories, PascalCase for React components, snake_case for Python
- **Variables**: camelCase (JS/TS), snake_case (Python), SCREAMING_SNAKE_CASE for constants
- **Swedish Terms**: Use proper Swedish terminology (myndighetsdokument, propositioner, riksdagen)

### Critical Notes
- **Model Configuration**: Two-model system via llama-server with OpenAI-compatible API (port 8080):
  - Gemma 3 12B = BRAIN (GGUF format) (faktasvar)
  - GPT-SW3 6.7B = VOICE (GGUF format) (naturlig svenska)
- **Rate Limiting**: Always respect Swedish government site limits (5-10s between requests)
- **ChromaDB**: 535K+ documents indexed, use semantic search for legal document retrieval
- **Git Workflow**: This is NOT a git repository, use direct file operations
