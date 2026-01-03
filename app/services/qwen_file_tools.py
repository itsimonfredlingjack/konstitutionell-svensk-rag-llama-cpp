"""
Qwen-Agent File Tools Wrapper
=============================
Wraps existing system_tools.py file operations for use with Qwen-Agent.
Allows QWEN_AGENT to read files and list directories.
"""

import asyncio
from typing import Union

from qwen_agent.tools.base import BaseTool, register_tool

from .system_tools import system_tools
from ..utils.logging import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """Run async coroutine in sync context"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(coro)


@register_tool('file_read_tool')
class FileReadTool(BaseTool):
    """Tool for reading file contents on the server"""

    description = "Läs innehållet i en fil på servern (max 10KB). Användbart för att granska kod, konfigurationsfiler, loggar, etc."
    parameters = [{
        "name": "path",
        "type": "string",
        "description": "Absolut sökväg till filen som ska läsas, t.ex. /home/ai-server/app/main.py",
        "required": True
    }]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute file read operation"""
        # Handle both string and dict params
        if isinstance(params, str):
            import json
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {"path": params}

        path = params.get("path", "")
        if not path:
            return "Error: Ingen sökväg angiven"

        logger.info(f"FileReadTool: Reading {path}")

        try:
            result = _run_async(system_tools.execute("file_read", {"path": path}))
            if result.success:
                return result.output
            else:
                return f"Error: {result.error}"
        except Exception as e:
            logger.error(f"FileReadTool error: {e}")
            return f"Error: {str(e)}"


@register_tool('file_list_tool')
class FileListTool(BaseTool):
    """Tool for listing directory contents"""

    description = "Lista filer och mappar i en katalog på servern. Visar filtyp, storlek och namn."
    parameters = [{
        "name": "path",
        "type": "string",
        "description": "Absolut sökväg till katalogen som ska listas, t.ex. /home/ai-server/",
        "required": True
    }]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute directory listing"""
        # Handle both string and dict params
        if isinstance(params, str):
            import json
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {"path": params}

        path = params.get("path", "")
        if not path:
            return "Error: Ingen sökväg angiven"

        logger.info(f"FileListTool: Listing {path}")

        try:
            result = _run_async(system_tools.execute("file_list", {"path": path}))
            if result.success:
                return result.output
            else:
                return f"Error: {result.error}"
        except Exception as e:
            logger.error(f"FileListTool error: {e}")
            return f"Error: {str(e)}"


@register_tool('file_exists_tool')
class FileExistsTool(BaseTool):
    """Tool for checking if a file or directory exists"""

    description = "Kontrollera om en fil eller katalog finns på servern."
    parameters = [{
        "name": "path",
        "type": "string",
        "description": "Absolut sökväg att kontrollera",
        "required": True
    }]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute file exists check"""
        # Handle both string and dict params
        if isinstance(params, str):
            import json
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {"path": params}

        path = params.get("path", "")
        if not path:
            return "Error: Ingen sökväg angiven"

        logger.info(f"FileExistsTool: Checking {path}")

        try:
            result = _run_async(system_tools.execute("file_exists", {"path": path}))
            if result.success:
                return result.output
            else:
                return f"Error: {result.error}"
        except Exception as e:
            logger.error(f"FileExistsTool error: {e}")
            return f"Error: {str(e)}"


@register_tool('file_write_tool')
class FileWriteTool(BaseTool):
    """Tool for writing files to the server"""

    description = "Skriv innehåll till en fil på servern. Kan skapa nya filer eller skriva över befintliga. Tillåtna sökvägar: /home/ai-server, /tmp, /var/log, /etc/nginx, /opt"
    parameters = [
        {
            "name": "path",
            "type": "string",
            "description": "Absolut sökväg till filen som ska skrivas, t.ex. /tmp/test.py",
            "required": True
        },
        {
            "name": "content",
            "type": "string",
            "description": "Innehållet som ska skrivas till filen",
            "required": True
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute file write operation"""
        # Handle both string and dict params
        if isinstance(params, str):
            import json
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                return "Error: Kunde inte tolka parametrar som JSON"

        path = params.get("path", "")
        content = params.get("content", "")

        if not path:
            return "Error: Ingen sökväg angiven"
        if not content:
            return "Error: Inget innehåll angivet"

        logger.info(f"FileWriteTool: Writing to {path}")

        try:
            result = _run_async(system_tools.execute("file_write", {"path": path, "content": content}))
            if result.success:
                return result.output
            else:
                return f"Error: {result.error}"
        except Exception as e:
            logger.error(f"FileWriteTool error: {e}")
            return f"Error: {str(e)}"


# Tool instances for use in qwen_agent_provider.py
file_read_tool = FileReadTool()
file_list_tool = FileListTool()
file_exists_tool = FileExistsTool()
file_write_tool = FileWriteTool()

# List of all file tools
FILE_TOOLS = [file_read_tool, file_list_tool, file_exists_tool, file_write_tool]
