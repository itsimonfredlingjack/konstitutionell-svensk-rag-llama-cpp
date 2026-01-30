# rag-cli

An Agentic AI coding assistant with a Textual TUI.

## Installation

```bash
pip install -e .
```

## Usage

```bash
rag
```

## Providers (Ollama)

Create `~/.config/rag-cli/config.toml`:

```toml
default_provider = "ollama"

[providers.ollama]
type = "ollama"
model = "granite3.1-dense:2b"
base_url = "http://localhost:11434"
auto_switch = true
small_model = "granite3.1-dense:2b"
large_model = "granite3.1-dense:8b"
keep_alive = 0
```

## Tool Plugins

Drop Python files in `.rag-cli/tools/`. Each file can expose either:

- `load_tools()` returning a `Tool` instance or a list of `Tool` instances
- `TOOLS` list of `Tool` instances
