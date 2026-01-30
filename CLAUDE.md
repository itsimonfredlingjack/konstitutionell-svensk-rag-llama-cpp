# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibe-CLI is an agentic AI coding assistant with a Textual TUI. It provides an interactive terminal interface for LLM-powered code manipulation with built-in security controls.

## Commands

```bash
# Create venv and install for development
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run the application
vibe

# Run tests
pytest -xvs

# Run single test file
pytest tests/test_models.py -xvs

# Lint and format
ruff check --fix .
ruff format .
```

## Architecture

```
vibe_cli/
├── __main__.py          # Entry point
├── config.py            # TOML-based hierarchical config
├── agent/
│   ├── loop.py          # Core agentic loop (LLM → tools → repeat)
│   ├── context.py       # Token management and compression
│   └── checkpoint.py    # Conversation state snapshots
├── models/
│   ├── messages.py      # Message, ToolCall, ToolResult, Conversation
│   └── tools.py         # ToolDefinition with OpenAI/Anthropic schema export
├── providers/
│   ├── base.py          # LLMProvider abstract interface
│   └── openai_compat.py # OpenAI-compatible streaming client
├── tools/
│   ├── base.py          # Tool and ToolRegistry abstractions
│   ├── filesystem.py    # ReadFile, WriteFile, StrReplace
│   ├── shell.py         # ShellTool with allowlist/blocklist
│   └── git.py           # GitStatus, GitAdd, GitCommit
└── ui/
    ├── app.py           # VibeApp (Textual TUI)
    ├── theme.py         # Neon color scheme and ASCII art
    └── widgets.py       # Chat, Avatar, TypingIndicator
```

### Key Patterns

- **Async throughout**: All I/O uses httpx, aiofiles, asyncio subprocess
- **Streaming**: LLM responses stream to UI in real-time via `StreamChunk` yields
- **Tool registry**: Tools self-register with `ToolDefinition` schemas
- **Provider abstraction**: `LLMProvider` base class supports multiple backends
- **Security layers**: Path traversal prevention, command allowlisting, dangerous tool confirmation

### Agent Loop Flow

1. User message added to conversation
2. LLM response streamed and parsed for tool calls
3. Tools executed (with confirmation if dangerous)
4. Tool results added to conversation
5. Repeat until no tool calls or max iterations

### Configuration

Config loads from `~/.config/vibe/config.toml` with sections:
- `provider`: API endpoint, model, tokens, key
- `ui`: Theme, confirmations
- `context`: Token limits, compression threshold (70%)
- `shell`: Allowed commands, blocked patterns, timeout
- `agent`: Max iterations, confirmation settings

Default provider: Local model at `http://localhost:8080/v1` with `phi-4`

## Tool Security

All filesystem tools enforce workspace boundary checks. Shell commands use:
- **Allowlist**: `["ls", "cat", "grep", "git", "pytest", "npm", "echo", "pwd", "mkdir", "touch"]`
- **Blocklist patterns**: `["rm -rf", "> /dev/", "sudo"]`

Tools marked `dangerous=True` require user confirmation: `write_file`, `str_replace`, `run_command`, `git_commit`

## UI Slash Commands

- `/checkpoint [description]` - Create conversation checkpoint
- `/clear` - Clear conversation
- `/help` - Show available commands

Checkpoints save to `.vibe/checkpoints/` with conversation JSON and tracked file copies.

## Testing

Tests use pytest with pytest-asyncio. Run with:
```bash
pytest -xvs                    # All tests, verbose, stop on first failure
pytest --tb=short              # Shorter tracebacks
pytest -k "test_read"          # Run tests matching pattern
```
