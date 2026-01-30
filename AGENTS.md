# AGENTS.md

This file guides agentic coding assistants working in the vibe-cli repository.

## Commands

```bash
# Setup development environment
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run the application
vibe

# Run all tests
pytest -xvs

# Run single test file
pytest tests/test_models.py -xvs

# Run specific test
pytest -xvs -k test_message_serialization

# Lint and format
ruff check --fix .
ruff format .
```

## Code Style

### Python Requirements
- Minimum Python 3.11
- Type hints required for all function signatures
- Line length: 120 characters
- Use `|` union syntax over `Optional` or `Union` (e.g., `str | None`)

### Imports
Group imports in order: stdlib, third-party, local. Separate groups with blank line.
```python
from pathlib import Path
from typing import AsyncIterator

import httpx
from pydantic import BaseModel

from vibe_cli.models.messages import Message
from vibe_cli.tools.base import Tool
```

### Naming Conventions
- Classes: PascalCase (`AgentLoop`, `OpenAICompatProvider`)
- Functions and variables: snake_case (`run_command`, `full_path`)
- Constants: UPPER_SNAKE_CASE
- Private members: single underscore prefix (`_tools`)

### Type Annotations
```python
# Function signatures
async def execute(self, path: str, start_line: int = 1, end_line: int = -1) -> ToolResult:

# Type hints for variables
messages: List[Message] = []
tool: Tool | None = None

# Abstract methods
@property
@abstractmethod
def definition(self) -> ToolDefinition:
    ...
```

### Data Models
Use Pydantic BaseModel for all data structures:
```python
from pydantic import BaseModel, Field

class Message(BaseModel):
    role: Role
    content: str | list[dict]
    timestamp: datetime = Field(default_factory=datetime.now)
```

### Async I/O
All I/O operations must be async:
- Use `httpx` for HTTP (not `requests`)
- Use `aiofiles` for file operations
- Use `asyncio.create_subprocess_shell` for shell commands
- Use `async with` for context managers

### Error Handling
```python
# Tools: Return ToolResult with is_error=True
try:
    result = await operation()
    return ToolResult(tool_call_id="", content="Success", is_error=False)
except Exception as e:
    return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)

# Other code: Raise exceptions
if not condition:
    raise ValueError(f"Invalid state: {reason}")
```

### File Paths
Always use `pathlib.Path`, never `os.path`:
```python
from pathlib import Path

workspace = Path.cwd()
full_path = (workspace / relative_path).resolve()

# Security: verify path stays within workspace
if not str(full_path).startswith(str(workspace.resolve())):
    raise SecurityError("Path escapes workspace")
```

### String Formatting
Use f-strings exclusively:
```python
message = f"File {path} not found"
lines = content.count("\n") + 1
```

### Abstract Base Classes
Use `@abstractmethod` for interface enforcement:
```python
from abc import ABC, abstractmethod

class Tool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        ...
```

## Testing

Tests use pytest with pytest-asyncio. Test files in `tests/` directory.

```python
def test_feature_scenario():
    # Arrange
    msg = Message(role=Role.USER, content="Hello")

    # Act
    result = process(msg)

    # Assert
    assert result.role == Role.USER
    assert result.content == "Hello"
```

## Architecture Notes

- **Agent loop**: AsyncIterator yields StreamChunk for streaming, ToolResult for tool outputs
- **Tool registry**: Tools register via `ToolDefinition` schemas, execute via `ToolRegistry.execute()`
- **Security**: Path traversal checks, command allowlist/blocklist, dangerous tool confirmation
- **Context management**: Token counting and compression at 70% threshold

## Configuration

Config loads from `~/.config/vibe/config.toml`. Do not commit secrets.
