# rag-cli

**rag-cli** is an Agentic AI coding assistant with a terminal-based user interface (TUI) built using Textual. It empowers developers to interact with a remote RAG agent directly from their terminal.

## Project Overview

*   **Type:** Python CLI Application (Thin Client)
*   **Core Frameworks:** Textual (UI), Rich (Formatting), Pydantic (Data Validation), HTTPX (Async Networking).
*   **Goal:** Provide a secure, extensible, and interactive terminal environment for AI-assisted development.

## Architecture

The project is structured as follows:

*   **`rag_cli/`**: The main package directory.
    *   **`__main__.py`**: Entry point for the application.
    *   **`config.py`**: Handles configuration loading from `~/.config/rag-cli/config.toml`.
    *   **`providers/`**: Backend integration.
        *   `rag_backend.py`: Client for the remote SSE-based RAG agent.
    *   **`ui/`**: Textual-based user interface.
        *   `app.py`: Main application class `RagApp`.
        *   `widgets.py`: Custom widgets like Chat view, Input area.
        *   `theme.py`: UI styling and ASCII art.

## Setup and Usage

### Installation

1.  **Create a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
2.  **Install dependencies (editable mode):**
    ```bash
    pip install -e ".[dev]"
    ```

### Running the Application

To start the CLI:
```bash
rag
```

### Configuration

Configuration is stored in `~/.config/rag-cli/config.toml`.

Example `config.toml`:
```toml
rag_backend_url = "http://localhost:8900"

[ui]
theme = "light"
```

## Development Workflow

### Testing

Run tests using `pytest`:

```bash
# Run all tests
pytest -xvs
```

### Linting and Formatting

The project uses `ruff`:

```bash
# Lint
ruff check --fix .

# Format
ruff format .
```

## Key Files for Context

*   **`rag_cli/ui/app.py`**: The entry point for the TUI, managing application lifecycle.
*   **`rag_cli/providers/rag_backend.py`**: Handles connection to the AI backend.
*   **`CLAUDE.md`**: Contains detailed architectural notes and context for AI assistants.
