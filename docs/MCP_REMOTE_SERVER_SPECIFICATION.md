# MCP Remote Server Specification & Implementation Guide

## Document Version
**Last Updated:** 2025-12-03
**MCP Spec Version:** 2025-11-25 (Latest Anniversary Release)
**Target:** Claude.ai Web Interface Integration

---

## Table of Contents

1. [Protocol Overview](#protocol-overview)
2. [Transport Mechanisms](#transport-mechanisms)
3. [Authentication](#authentication)
4. [Core Components](#core-components)
5. [Python Implementation with FastMCP](#python-implementation-with-fastmcp)
6. [HTTP Endpoints & JSON-RPC](#http-endpoints--json-rpc)
7. [Tool Definitions](#tool-definitions)
8. [Claude.ai Integration](#claudeai-integration)
9. [Security & Best Practices](#security--best-practices)
10. [Complete Code Examples](#complete-code-examples)

---

## Protocol Overview

### What is MCP?

Model Context Protocol (MCP) is an open standard introduced by Anthropic in November 2024 to standardize how AI systems like LLMs integrate with external data sources and tools.

### Key Capabilities

MCP servers expose three types of capabilities:

1. **Tools** - Executable functions that can be invoked by LLMs to perform actions
2. **Resources** - Data sources (files, database schemas, etc.) to feed into LLM context
3. **Prompts** - Reusable, structured prompt templates for LLMs

### Latest Specification Updates

**2025-11-25 (Anniversary Release):**
- **Tasks**: New abstraction for tracking work performed by MCP servers
- **Tool Calling in Sampling**: Servers can now include tool definitions and specify tool choice behavior
- Multi-step reasoning with server-side agent loops
- Parallel tool calls support

**2025-06-18 Release:**
- **OAuth Resource Servers**: Implementation of Resource Indicators (RFC 8707)
- **Structured Tool Outputs**: Improved type safety
- **Elicitation**: Server-initiated user interactions
- Enhanced security best practices

### Official Specification
- **URL:** https://modelcontextprotocol.io/specification/2025-06-18
- **TypeScript Schema:** Source of truth at `schema.ts`
- **JSON Schema:** Auto-generated from TypeScript for tooling

---

## Transport Mechanisms

### Recommended: Streamable HTTP (2025-03-26 Spec)

**Why Streamable HTTP?**
- Single endpoint pattern (POST /mcp)
- Better cost efficiency than legacy HTTP+SSE
- Enables serverless platforms to scale to zero when idle
- Supported by TypeScript SDK 1.10.0+ (released April 17, 2025)

**Connection Pattern:**
```
Client → POST /mcp → Server
Server → Response (JSON or SSE stream)
```

**Session Management:**
- Server assigns session ID during initialization
- `Mcp-Session-Id` header in response
- Client includes session ID in subsequent request headers

### Legacy: HTTP+SSE (Deprecated 2024-11-05)

**Connection Pattern:**
```
Client → GET /sse → Server (persistent SSE connection)
Client → POST /sse/messages → Server (requests)
```

**Issues:**
- Requires persistent connections
- Prevents serverless scaling to zero
- Two separate endpoints to maintain

**Status:** Being phased out, Streamable HTTP recommended for new implementations

---

## Authentication

### OAuth with Dynamic Client Registration (DCR)

**CRITICAL:** Claude.ai **requires** full compatibility with Dynamic Client Registration (RFC 7591).

**Why DCR?**
- Unlike traditional OAuth with static client credentials
- Enables third-party clients to obtain credentials programmatically
- Standards-compliant registration and discovery endpoints

**Required OAuth Features:**
- **Resource Indicators** (RFC 8707) - prevents malicious servers from obtaining access tokens
- **Dynamic Client Registration** (RFC 7591) - programmatic client credential issuance
- Token scoping to specific MCP server audience

**Authentication Flow:**
1. Client initiates DCR with authorization server
2. Receives dynamic client credentials
3. Uses Resource Indicators in token request
4. Authorization server issues tightly-scoped token
5. Token only valid for specific MCP server

### API Key Authentication

**Support Status:** Limited - OAuth/DCR is strongly preferred for production

**If Using API Keys:**
- Use environment variables for sensitive data
- Implement proper token rotation
- Add rate limiting and request throttling
- Validate all inputs and responses
- Log security events

**Claude.ai Compatibility:** Check if your use case allows API key auth instead of OAuth

---

## Core Components

### Tools

**Purpose:** Expose executable functions that LLMs can invoke to perform actions

**Discovery:** `tools/list` endpoint
**Invocation:** `tools/call` endpoint
**Flexibility:** From simple calculations to complex API interactions

**When to Use:**
- Performing actions (write file, execute command)
- Fetching dynamic data (API calls, database queries)
- Calculations and transformations
- External system integration

### Resources

**Purpose:** Expose data sources to feed info into LLM context

**Characteristics:**
- Each resource has a unique URI
- Can be local or remote data
- Provides context to language models

**Examples:**
- File contents (`file:///path/to/file`)
- Database schemas (`schema://database_name`)
- API documentation (`docs://api/endpoint`)
- Application-specific data

**When to Use:**
- Providing static or semi-static context
- Database schemas for query generation
- Documentation for code generation
- Configuration data

### Prompts

**Purpose:** Define reusable, structured prompt templates

**Characteristics:**
- Tailored to specific tasks
- Include customizable arguments
- Help LLMs interact more effectively

**Examples:**
- Code review templates
- Documentation generation prompts
- Analysis frameworks

**When to Use:**
- Standardizing common workflows
- Ensuring consistent LLM behavior
- Complex multi-step reasoning patterns

---

## Python Implementation with FastMCP

### Why FastMCP?

FastMCP is the **recommended** Python framework for building MCP servers:

- High-level, Pythonic interface
- Handles all protocol details automatically
- HTTP transport support for web deployment
- Enterprise-grade authentication
- Async-first design (supports both sync and async)

### Installation

```bash
pip install fastmcp
```

### Alternative Options

1. **Official MCP Python SDK** - Lower-level, full protocol implementation
2. **fastapi-mcp** - Lightweight library specifically for FastAPI integration (first to support MCP auth spec)

---

## HTTP Endpoints & JSON-RPC

### Protocol: JSON-RPC 2.0

All MCP communication uses JSON-RPC 2.0 format.

### Standard Request Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "method_name",
  "params": {
    "param1": "value1"
  }
}
```

### Standard Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "data": "response_data"
  }
}
```

### Error Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": "Additional error details"
  }
}
```

### Key Endpoints

#### 1. Initialize Connection

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": {},
      "resources": {},
      "prompts": {}
    },
    "clientInfo": {
      "name": "claude-client",
      "version": "1.0.0"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": {},
      "resources": {},
      "prompts": {}
    },
    "serverInfo": {
      "name": "my-mcp-server",
      "version": "1.0.0"
    }
  }
}
```

#### 2. List Available Tools

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "read_file",
        "description": "Read contents of a file",
        "inputSchema": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "File path to read"
            }
          },
          "required": ["path"]
        }
      }
    ]
  }
}
```

#### 3. Call a Tool

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {
      "path": "/path/to/file.txt"
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "File contents here..."
      }
    ]
  }
}
```

#### 4. List Resources

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "resources/list",
  "params": {}
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "resources": [
      {
        "uri": "file:///project/README.md",
        "name": "Project README",
        "description": "Main project documentation",
        "mimeType": "text/markdown"
      }
    ]
  }
}
```

#### 5. Read Resource

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "resources/read",
  "params": {
    "uri": "file:///project/README.md"
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "contents": [
      {
        "uri": "file:///project/README.md",
        "mimeType": "text/markdown",
        "text": "# Project Title\n\nProject documentation..."
      }
    ]
  }
}
```

---

## Tool Definitions

### JSON Schema (Draft 2020-12)

Each tool declares its parameters using JSON Schema, enabling type-safe invocations.

### Parameter Types

**Required Parameters:** No default value
```python
def search(query: str):  # query is required
    pass
```

**Optional Parameters:** Has default value
```python
def search(query: str, max_results: int = 10):  # max_results is optional
    pass
```

### FastMCP Tool Definition Examples

#### Basic Tool

```python
from fastmcp import FastMCP

mcp = FastMCP("Demo Server")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together"""
    return a + b
```

**Generated JSON Schema:**
```json
{
  "name": "add",
  "description": "Add two numbers together",
  "inputSchema": {
    "type": "object",
    "properties": {
      "a": {"type": "integer"},
      "b": {"type": "integer"}
    },
    "required": ["a", "b"]
  }
}
```

#### Complex Tool with Optional Parameters

```python
@mcp.tool()
def search_products(
    query: str,  # Required
    max_results: int = 10,  # Optional with default
    sort_by: str = "relevance",  # Optional with default
    category: str | None = None  # Optional, can be None
) -> list[dict]:
    """
    Search the product catalog.

    Args:
        query: Search query string
        max_results: Maximum number of results to return
        sort_by: Sort order (relevance, price, rating)
        category: Filter by category
    """
    # Implementation...
    results = []
    return results
```

**Generated JSON Schema:**
```json
{
  "name": "search_products",
  "description": "Search the product catalog.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query string"
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum number of results to return",
        "default": 10
      },
      "sort_by": {
        "type": "string",
        "description": "Sort order (relevance, price, rating)",
        "default": "relevance"
      },
      "category": {
        "type": ["string", "null"],
        "description": "Filter by category"
      }
    },
    "required": ["query"]
  }
}
```

#### Async Tool (Recommended for I/O)

```python
import aiofiles

@mcp.tool()
async def read_file_async(path: str) -> str:
    """Read file contents asynchronously"""
    async with aiofiles.open(path, 'r') as f:
        contents = await f.read()
    return contents
```

---

## Claude.ai Integration

### Adding Remote MCP Server

#### Via Claude Web Interface

1. Navigate to **Settings > Connectors**
2. Click **"Add custom connector"** at the bottom
3. Enter your remote MCP server URL
4. (Optional) Click **"Advanced settings"** for OAuth credentials
5. Click **"Add"** to complete connection

#### URL Format

**Standard HTTPS:**
```
https://api.example.com/mcp
```

**With Path:**
```
https://api.example.com/v1/mcp
```

#### Configuration Requirements

**Account Tier:** Requires Max, Team, or Enterprise plan (not available on free tier)

**Supported Transports:**
- Streamable HTTP (recommended)
- HTTP+SSE (legacy, may be deprecated soon)

### Claude Desktop Configuration

For Claude Desktop, edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-remote-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-mcp-server-url.com"
      ]
    }
  }
}
```

### Testing & Debugging

**Connection Test:**
1. Add server URL in Claude settings
2. Start a new conversation
3. Ask Claude to list available tools
4. Verify tools appear in Claude's context

**Debug Checklist:**
- ✓ HTTPS enabled (not HTTP)
- ✓ CORS headers configured correctly
- ✓ Authentication working (OAuth or API key)
- ✓ Server responding to initialize request
- ✓ Tools/resources properly registered
- ✓ JSON-RPC format correct

---

## Security & Best Practices

### Authentication Security

**OAuth Best Practices:**
- Implement Dynamic Client Registration (DCR)
- Use Resource Indicators to scope tokens
- Never expose client secrets in frontend code
- Rotate tokens regularly
- Validate token audience and scope

**API Key Best Practices:**
- Store keys in environment variables
- Never commit keys to version control
- Implement rate limiting per key
- Log all authenticated requests
- Implement key rotation mechanism

### Input Validation

**Always Validate:**
- Tool parameters against JSON schema
- File paths (prevent directory traversal)
- Command injection risks
- SQL injection risks (if using databases)
- Resource URIs

**Example:**
```python
import os
from pathlib import Path

def validate_file_path(path: str, base_dir: str) -> Path:
    """Validate file path is within allowed directory"""
    base = Path(base_dir).resolve()
    target = (base / path).resolve()

    if not str(target).startswith(str(base)):
        raise ValueError("Path traversal attempt detected")

    return target
```

### Rate Limiting

**Implement at Multiple Levels:**
- Per API key/OAuth token
- Per IP address
- Per tool/resource
- Global server limits

**Example with FastAPI:**
```python
from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/mcp")
@limiter.limit("10/minute")
async def mcp_endpoint(request: Request):
    # Handle MCP requests
    pass
```

### CORS Configuration

**Required for Web Access:**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://claude.ai",
        "https://*.claude.ai",
        "https://console.anthropic.com"
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)
```

### Error Handling

**Graceful Degradation:**
```python
from fastapi import HTTPException

@mcp.tool()
def read_file(path: str) -> str:
    """Read file contents safely"""
    try:
        validated_path = validate_file_path(path, BASE_DIR)
        with open(validated_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as e:
        # Log error for debugging
        logger.error(f"Error reading file {path}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Logging & Monitoring

**Log Important Events:**
- Authentication attempts (success/failure)
- Tool invocations with parameters
- Errors and exceptions
- Rate limit hits
- Unusual patterns

**Security Events to Monitor:**
- Failed authentication attempts
- Path traversal attempts
- Rate limit violations
- Unexpected tool parameters
- Repeated errors from same client

---

## Complete Code Examples

### Example 1: Basic File Operations Server

```python
from fastmcp import FastMCP
from pathlib import Path
import os
from typing import List

mcp = FastMCP("File Operations MCP")

# Configure base directory for file operations
BASE_DIR = Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD")

def validate_path(path: str) -> Path:
    """Validate and resolve file path within base directory"""
    base = BASE_DIR.resolve()
    target = (base / path).resolve()

    if not str(target).startswith(str(base)):
        raise ValueError(f"Access denied: Path outside base directory")

    return target

@mcp.tool()
def read_file(path: str) -> str:
    """
    Read contents of a file.

    Args:
        path: Relative path to file from base directory

    Returns:
        File contents as string
    """
    try:
        validated_path = validate_path(path)

        if not validated_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not validated_path.is_file():
            raise ValueError(f"Not a file: {path}")

        with open(validated_path, 'r', encoding='utf-8') as f:
            return f.read()

    except Exception as e:
        return f"Error reading file: {str(e)}"

@mcp.tool()
def write_file(path: str, content: str) -> str:
    """
    Write content to a file.

    Args:
        path: Relative path to file from base directory
        content: Content to write to file

    Returns:
        Success message
    """
    try:
        validated_path = validate_path(path)

        # Create parent directories if they don't exist
        validated_path.parent.mkdir(parents=True, exist_ok=True)

        with open(validated_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"Successfully wrote {len(content)} characters to {path}"

    except Exception as e:
        return f"Error writing file: {str(e)}"

@mcp.tool()
def list_directory(path: str = ".") -> List[dict]:
    """
    List contents of a directory.

    Args:
        path: Relative path to directory from base directory

    Returns:
        List of files and directories with metadata
    """
    try:
        validated_path = validate_path(path)

        if not validated_path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not validated_path.is_dir():
            raise ValueError(f"Not a directory: {path}")

        items = []
        for item in sorted(validated_path.iterdir()):
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
                "modified": item.stat().st_mtime
            })

        return items

    except Exception as e:
        return [{"error": str(e)}]

@mcp.resource("file://project/structure")
def get_project_structure() -> str:
    """Provide project directory structure as a resource"""
    try:
        structure = []
        for root, dirs, files in os.walk(BASE_DIR):
            level = root.replace(str(BASE_DIR), '').count(os.sep)
            indent = ' ' * 2 * level
            structure.append(f'{indent}{os.path.basename(root)}/')
            sub_indent = ' ' * 2 * (level + 1)
            for file in files:
                structure.append(f'{sub_indent}{file}')

        return '\n'.join(structure[:100])  # Limit to first 100 lines

    except Exception as e:
        return f"Error generating structure: {str(e)}"
```

### Example 2: Git Operations Server

```python
from fastmcp import FastMCP
import subprocess
from pathlib import Path
from typing import List, Dict

mcp = FastMCP("Git Operations MCP")

REPO_PATH = Path("/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD")

def run_git_command(args: List[str]) -> Dict[str, str]:
    """
    Run a git command safely.

    Args:
        args: Git command arguments

    Returns:
        Dict with stdout, stderr, and return_code
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=REPO_PATH,
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "success": result.returncode == 0
        }

    except subprocess.TimeoutExpired:
        return {
            "error": "Command timed out",
            "success": False
        }
    except Exception as e:
        return {
            "error": str(e),
            "success": False
        }

@mcp.tool()
def git_status() -> str:
    """
    Get current git status.

    Returns:
        Git status output
    """
    result = run_git_command(["status"])

    if result["success"]:
        return result["stdout"]
    else:
        return f"Error: {result.get('stderr', result.get('error', 'Unknown error'))}"

@mcp.tool()
def git_diff(file_path: str = "") -> str:
    """
    Get git diff for file or entire repository.

    Args:
        file_path: Optional specific file path to diff

    Returns:
        Git diff output
    """
    args = ["diff"]
    if file_path:
        args.append(file_path)

    result = run_git_command(args)

    if result["success"]:
        return result["stdout"] or "No changes detected"
    else:
        return f"Error: {result.get('stderr', result.get('error', 'Unknown error'))}"

@mcp.tool()
def git_log(limit: int = 10) -> str:
    """
    Get recent git commit history.

    Args:
        limit: Number of commits to show (default: 10, max: 50)

    Returns:
        Git log output
    """
    # Clamp limit to reasonable range
    limit = max(1, min(limit, 50))

    result = run_git_command([
        "log",
        f"-{limit}",
        "--pretty=format:%h - %an, %ar : %s"
    ])

    if result["success"]:
        return result["stdout"]
    else:
        return f"Error: {result.get('stderr', result.get('error', 'Unknown error'))}"

@mcp.tool()
def git_branch() -> str:
    """
    List git branches.

    Returns:
        Git branch output
    """
    result = run_git_command(["branch", "-a"])

    if result["success"]:
        return result["stdout"]
    else:
        return f"Error: {result.get('stderr', result.get('error', 'Unknown error'))}"

@mcp.tool()
def git_commit(message: str, files: List[str] = []) -> str:
    """
    Commit changes to git.

    Args:
        message: Commit message
        files: List of files to commit (empty = all staged)

    Returns:
        Commit result
    """
    # Add files if specified
    if files:
        for file in files:
            result = run_git_command(["add", file])
            if not result["success"]:
                return f"Error adding {file}: {result.get('stderr', 'Unknown error')}"

    # Commit
    result = run_git_command(["commit", "-m", message])

    if result["success"]:
        return result["stdout"]
    else:
        return f"Error: {result.get('stderr', result.get('error', 'Unknown error'))}"

@mcp.resource("git://repository/info")
def get_repo_info() -> str:
    """Provide git repository information as a resource"""
    info = []

    # Current branch
    branch_result = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch_result["success"]:
        info.append(f"Current Branch: {branch_result['stdout'].strip()}")

    # Remote URL
    remote_result = run_git_command(["remote", "get-url", "origin"])
    if remote_result["success"]:
        info.append(f"Remote URL: {remote_result['stdout'].strip()}")

    # Last commit
    log_result = run_git_command(["log", "-1", "--pretty=format:%h - %an, %ar : %s"])
    if log_result["success"]:
        info.append(f"Last Commit: {log_result['stdout'].strip()}")

    return "\n".join(info)
```

### Example 3: FastAPI Integration with Authentication

```python
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastmcp import FastMCP
import os
from typing import Optional

# Initialize FastAPI app
app = FastAPI(title="MCP Remote Server")

# CORS configuration for Claude.ai
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://claude.ai",
        "https://*.claude.ai",
        "https://console.anthropic.com"
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# API Key authentication
security = HTTPBearer()
VALID_API_KEY = os.getenv("MCP_API_KEY", "your-secret-api-key")

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify API key from Authorization header"""
    if credentials.credentials != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials

# Initialize FastMCP
mcp = FastMCP("Authenticated MCP Server")

@mcp.tool()
def echo(message: str) -> str:
    """Echo a message back"""
    return f"Echo: {message}"

@mcp.tool()
def get_server_info() -> dict:
    """Get server information"""
    return {
        "server": "Authenticated MCP Server",
        "version": "1.0.0",
        "status": "running"
    }

# Mount MCP endpoint with authentication
@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Main MCP endpoint with API key authentication.
    Handles JSON-RPC requests according to MCP specification.
    """
    try:
        # Get request body
        body = await request.json()

        # Handle MCP request through FastMCP
        # (FastMCP handles JSON-RPC protocol internally)
        response = await mcp.handle_request(body)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint (no auth required)
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "server": "MCP Remote Server"}

# Run server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Example 4: Complete Production Server with OAuth

```python
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2AuthorizationCodeBearer
from fastmcp import FastMCP
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Production MCP Server",
    version="1.0.0",
    description="Production-ready MCP server with OAuth"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://claude.ai",
        "https://*.claude.ai",
        "https://console.anthropic.com"
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# OAuth2 configuration
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=os.getenv("OAUTH_AUTH_URL", "https://auth.example.com/oauth/authorize"),
    tokenUrl=os.getenv("OAUTH_TOKEN_URL", "https://auth.example.com/oauth/token")
)

async def verify_oauth_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verify OAuth token with authorization server.
    Implement according to your OAuth provider.
    """
    # TODO: Implement token verification with your OAuth provider
    # This should validate:
    # - Token signature
    # - Token expiration
    # - Token audience (Resource Indicators)
    # - Required scopes

    logger.info(f"Verifying OAuth token")

    # Placeholder - implement actual verification
    user_info = {
        "user_id": "user123",
        "scopes": ["mcp:read", "mcp:write"]
    }

    return user_info

# Initialize FastMCP
mcp = FastMCP("Production MCP Server")

# Define tools with comprehensive error handling
@mcp.tool()
async def analyze_project(path: str = ".") -> dict:
    """
    Analyze project structure and provide insights.

    Args:
        path: Project path to analyze

    Returns:
        Project analysis results
    """
    try:
        logger.info(f"Analyzing project at {path}")

        # Implement your analysis logic
        analysis = {
            "path": path,
            "files_count": 0,
            "directories_count": 0,
            "languages": [],
            "insights": []
        }

        return analysis

    except Exception as e:
        logger.error(f"Error analyzing project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@mcp.tool()
async def validate_code(code: str, language: str = "python") -> dict:
    """
    Validate code syntax and style.

    Args:
        code: Code to validate
        language: Programming language

    Returns:
        Validation results
    """
    try:
        logger.info(f"Validating {language} code")

        # Implement your validation logic
        validation = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": []
        }

        return validation

    except Exception as e:
        logger.error(f"Error validating code: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# MCP endpoint with OAuth and rate limiting
@app.post("/mcp")
@limiter.limit("30/minute")
async def mcp_endpoint(
    request: Request,
    user_info: dict = Depends(verify_oauth_token)
):
    """
    Main MCP endpoint with OAuth authentication and rate limiting.
    """
    try:
        logger.info(f"MCP request from user {user_info['user_id']}")

        # Get request body
        body = await request.json()

        # Log request for monitoring
        logger.debug(f"Request: {body.get('method', 'unknown')}")

        # Handle MCP request
        response = await mcp.handle_request(body)

        return response

    except Exception as e:
        logger.error(f"Error handling MCP request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# OAuth Dynamic Client Registration endpoint
@app.post("/oauth/register")
async def oauth_register(request: Request):
    """
    Dynamic Client Registration (RFC 7591).
    Required for Claude.ai integration.
    """
    try:
        body = await request.json()

        # Implement DCR according to RFC 7591
        # Return client credentials

        client_id = "generated_client_id"
        client_secret = "generated_client_secret"

        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_id_issued_at": 1234567890,
            "client_secret_expires_at": 0  # Never expires
        }

    except Exception as e:
        logger.error(f"Error in DCR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "server": "Production MCP Server",
        "version": "1.0.0"
    }

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Metrics endpoint for monitoring"""
    return {
        "requests_total": 0,  # Implement actual metrics
        "errors_total": 0,
        "tools_invoked": {}
    }

# Run server
if __name__ == "__main__":
    import uvicorn

    # Production configuration
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] HTTPS enabled (required for Claude.ai)
- [ ] OAuth/API key authentication configured
- [ ] CORS headers set correctly
- [ ] Rate limiting implemented
- [ ] Input validation for all tools
- [ ] Error handling with graceful degradation
- [ ] Logging configured
- [ ] Health check endpoint working

### Testing

- [ ] All tools tested individually
- [ ] Resources accessible
- [ ] Authentication working
- [ ] Rate limits enforced
- [ ] Error responses correct format
- [ ] JSON-RPC protocol compliance
- [ ] Session management working

### Production

- [ ] Monitoring configured
- [ ] Alerts set up
- [ ] Backup strategy in place
- [ ] Documentation complete
- [ ] Security audit completed
- [ ] Load testing performed
- [ ] Disaster recovery plan

### Claude.ai Integration

- [ ] Server URL added to Claude settings
- [ ] Authentication flow tested
- [ ] Tools appear in Claude context
- [ ] Tool invocations working
- [ ] Error messages clear to users
- [ ] Performance acceptable

---

## Troubleshooting

### Common Issues

**Issue:** Claude can't connect to server
**Solutions:**
- Verify HTTPS is enabled
- Check CORS configuration
- Confirm server is publicly accessible
- Test with curl/Postman first

**Issue:** Authentication fails
**Solutions:**
- Verify OAuth DCR implementation
- Check API key in environment variables
- Confirm token expiration handling
- Review authorization headers

**Issue:** Tools not appearing
**Solutions:**
- Confirm `tools/list` endpoint working
- Verify JSON schema is valid
- Check tool registration in FastMCP
- Review server logs for errors

**Issue:** Rate limit errors
**Solutions:**
- Adjust rate limit thresholds
- Implement per-user limits
- Add retry logic with backoff
- Monitor usage patterns

---

## Additional Resources

### Official Documentation
- [MCP Specification 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18)
- [MCP Official GitHub](https://github.com/modelcontextprotocol/modelcontextprotocol)
- [FastMCP GitHub](https://github.com/jlowin/fastmcp)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

### Guides & Tutorials
- [Building Custom Connectors via Remote MCP Servers](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [Connect to remote MCP Servers](https://modelcontextprotocol.io/docs/develop/connect-remote-servers)
- [Build MCP Servers in Python with FastMCP](https://mcpcat.io/guides/building-mcp-server-python-fastmcp/)
- [MCP Server with Authentication in Python using FastAPI](https://medium.com/@miki_45906/how-to-build-mcp-server-with-authentication-in-python-using-fastapi-8777f1556f75)

### Community & Examples
- [Model Context Protocol Servers Repository](https://github.com/modelcontextprotocol/servers)
- [Remote MCP Server with Auth Template](https://github.com/coleam00/remote-mcp-server-with-auth)
- [MCP Blog - Anniversary Update](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)

---

## Sources

This documentation was compiled from the following sources:

- [Specification - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18)
- [One Year of MCP: November 2025 Spec Release](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)
- [Model Context Protocol (MCP) Spec Updates from June 2025](https://auth0.com/blog/mcp-specs-update-all-about-auth/)
- [Building Custom Connectors via Remote MCP Servers](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [Connect to remote MCP Servers](https://modelcontextprotocol.io/docs/develop/connect-remote-servers)
- [FastMCP GitHub Repository](https://github.com/jlowin/fastmcp)
- [Tools - FastMCP](https://gofastmcp.com/servers/tools)
- [Build MCP Servers in Python with FastMCP - Complete Guide](https://mcpcat.io/guides/building-mcp-server-python-fastmcp/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Server and Client with SSE & The New Streamable HTTP](https://levelup.gitconnected.com/mcp-server-and-client-with-sse-the-new-streamable-http-d860850d9d9d)
- [Overview - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/basic)
- [How to effectively use prompts, resources, and tools in MCP](https://composio.dev/blog/how-to-effectively-use-prompts-resources-and-tools-in-mcp)

---

**Document End**
