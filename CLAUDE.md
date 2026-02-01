# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

rag-cli is a terminal chat client for the Constitutional AI RAG backend. It provides an interactive Textual TUI that sends queries to the FastAPI backend via SSE streaming and displays responses with source citations.

## Commands

```bash
# Create venv and install for development
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run the application (requires backend on localhost:8900)
rag

# Run tests
pytest -xvs

# Lint and format
ruff check --fix .
ruff format .
```

## Architecture

```
rag_cli/
├── __main__.py              # Entry point (rag command)
├── config.py                # TOML-based config from ~/.config/rag-cli/config.toml
├── providers/
│   ├── base.py              # StreamChunk model
│   └── rag_backend.py       # SSE client to Constitutional AI backend
└── ui/
    ├── app.py               # RagApp (Textual TUI) - main application
    ├── theme.py             # Color scheme and Pygments syntax styles
    └── widgets.py           # StatusBar, AgentHeader, MainframeBubble
```

### Data Flow

1. User types query in Input widget
2. `RagApp.process()` sends query to backend via `RAGBackendProvider.query()`
3. Backend streams SSE events (token, metadata, done, error)
4. Tokens are appended to assistant bubble in real-time
5. Sources displayed after response completes
6. Conversation history tracked for multi-turn context

### Key Components

- **RAGBackendProvider**: httpx SSE client that streams from `/api/constitutional/agent/query/stream`
- **RagApp**: Textual App with chat view, input, and status bar
- **MainframeBubble**: Rich-rendered message bubbles (user/assistant/system)
- **Config**: Pydantic model loading from TOML with `rag_backend_url` setting

### Configuration

Config loads from `~/.config/rag-cli/config.toml`:
- `rag_backend_url`: Backend URL (default: `http://localhost:8900`)
- `ui.theme`: Theme setting
- `ui.show_tokens`: Show token count in header

## Testing

Tests use pytest with pytest-asyncio:
```bash
pytest -xvs                    # All tests, verbose, stop on first failure
pytest --tb=short              # Shorter tracebacks
pytest -k "test_stream"        # Run tests matching pattern
```
