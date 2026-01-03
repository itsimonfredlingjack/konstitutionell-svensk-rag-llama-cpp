"""
Qwen-Agent Provider med Code Interpreter + MCP + Web Search
============================================================
Wrapper som integrerar Qwen-Agent med befintligt WebSocket-system.
Ger QWEN förmågan att:
- Exekvera Python-kod autonomt (Code Interpreter)
- Söka på webben (Web Search)
- Använda MCP-servers (Filesystem, etc.)
"""

import time
import asyncio
from typing import AsyncGenerator, Optional, List, Dict, Any
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from qwen_agent.agents import Assistant
from qwen_agent.tools import WebSearch
from ..utils.logging import get_logger
from .qwen_file_tools import FILE_TOOLS

logger = get_logger(__name__)

# Try to import MCP Manager (optional)
try:
    from qwen_agent.tools.mcp_manager import MCPManager
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("MCPManager not available - MCP features disabled")

# Thread pool for running synchronous qwen-agent code
_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class QwenAgentStats:
    """Statistics from Qwen-Agent execution"""
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    total_duration_ms: int = 0
    code_executed: bool = False
    tool_calls: int = 0


class QwenAgentProvider:
    """
    Provider för Qwen-Agent med Code Interpreter, MCP och Web Search.

    Använder Ollama som backend och ger tillgång till:
    - code_interpreter: Kör Python-kod direkt
    - web_search: Sök på webben
    - file tools: Läs/skriv filer
    - MCP servers: Externa verktyg (filesystem, etc.)
    """

    def __init__(self):
        self.llm_cfg = {
            'model': 'devstral:24b',  # Devstral 24B - Code Interpreter
            'model_server': 'http://localhost:11434/v1',
            'api_key': 'ollama',
            'generate_cfg': {
                'max_input_tokens': 8192,
                'max_retries': 3,
            }
        }

        # Initialize MCP Manager if available
        self.mcp_manager = None
        if MCP_AVAILABLE:
            try:
                self.mcp_manager = MCPManager()
                logger.info("MCPManager initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize MCPManager: {e}")

        # Build function list:
        # 1. Code Interpreter (built-in)
        # 2. Web Search
        # 3. File Tools (custom)
        self.function_list = [
            'code_interpreter',
            WebSearch(),
        ] + FILE_TOOLS

        logger.info(f"QwenAgentProvider initialized with {len(self.function_list)} tools")

    def _create_assistant(self, system_prompt: str) -> Assistant:
        """Create a fresh Assistant instance"""
        return Assistant(
            function_list=self.function_list,
            llm=self.llm_cfg,
            name='QWEN AGENT',
            description='Elite coder med Code Interpreter',
            system_message=system_prompt
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        request_id: str
    ) -> AsyncGenerator[tuple[str, Optional[QwenAgentStats]], None]:
        """
        Stream response från Qwen-Agent med Code Interpreter support.

        Args:
            messages: Lista med {"role": "user/assistant", "content": "..."}
            system_prompt: System message för agenten
            request_id: Unik request ID för logging

        Yields:
            (token_text, None) för streaming
            ("", QwenAgentStats) som sista yield med statistik
        """
        logger.info(f"[{request_id}] QwenAgentProvider: Starting chat with Code Interpreter")

        start_time = time.time()
        token_count = 0
        tool_calls = 0
        code_executed = False
        last_content = ""

        try:
            assistant = self._create_assistant(system_prompt)

            # Konvertera messages till qwen-agent format
            qwen_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    continue  # System message hanteras separat
                qwen_messages.append({"role": role, "content": content})

            # Kör qwen-agent i thread pool (assistant.run() är synkron)
            loop = asyncio.get_event_loop()

            def run_agent():
                """Synkron körning av qwen-agent"""
                results = []
                for response in assistant.run(messages=qwen_messages):
                    if response:
                        results.append(response)
                return results

            # Kör i bakgrunden och streama resultat
            all_responses = await loop.run_in_executor(_executor, run_agent)

            # Processa alla responses
            for response_list in all_responses:
                if not response_list:
                    continue

                last_msg = response_list[-1]

                # Kolla om det finns tool calls
                if last_msg.get("function_call"):
                    tool_calls += 1
                    code_executed = True
                    logger.debug(f"[{request_id}] Tool call detected: {last_msg.get('function_call', {}).get('name', 'unknown')}")

                # Extrahera content
                content = last_msg.get("content", "")
                if isinstance(content, str) and content and content != last_content:
                    # Streama ny content
                    new_content = content[len(last_content):]
                    if new_content:
                        token_count += len(new_content.split())
                        yield new_content, None
                    last_content = content

            # Beräkna statistik
            duration_ms = int((time.time() - start_time) * 1000)
            tokens_per_sec = token_count / (duration_ms / 1000) if duration_ms > 0 else 0

            logger.info(
                f"[{request_id}] QwenAgentProvider: Completed - "
                f"tokens={token_count}, tool_calls={tool_calls}, "
                f"duration={duration_ms}ms, speed={tokens_per_sec:.1f} t/s"
            )

            # Yield final stats
            yield "", QwenAgentStats(
                tokens_generated=token_count,
                tokens_per_second=tokens_per_sec,
                total_duration_ms=duration_ms,
                code_executed=code_executed,
                tool_calls=tool_calls
            )

        except Exception as e:
            logger.error(f"[{request_id}] QwenAgentProvider error: {e}")
            # Yield error message
            yield f"\n\n[ERROR] Code Interpreter failed: {str(e)}", None

            # Yield stats anyway
            duration_ms = int((time.time() - start_time) * 1000)
            yield "", QwenAgentStats(
                tokens_generated=token_count,
                tokens_per_second=0,
                total_duration_ms=duration_ms,
                code_executed=code_executed,
                tool_calls=tool_calls
            )


# =============================================================================
# DOCKER SANDBOX EXECUTOR (Grok tip: Säker kodexekvering)
# =============================================================================

class DockerSandbox:
    """
    Säker kodexekvering i Docker-container.
    Isolerar kod från värdmaskinen med:
    - Ingen nätverksåtkomst (--network=none)
    - Begränsad RAM (--memory)
    - Begränsad CPU (--cpus)
    - Icke-root användare
    """

    def __init__(
        self,
        image: str = "ai-sandbox",
        memory_limit: str = "512m",
        cpu_limit: float = 0.5,
        timeout: int = 30
    ):
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.timeout = timeout

    async def execute(self, code: str) -> Dict[str, Any]:
        """
        Kör Python-kod i isolerad Docker-container.

        Args:
            code: Python-kod att köra

        Returns:
            {"success": bool, "output": str, "error": str, "duration_ms": int}
        """
        import tempfile
        import time

        start_time = time.time()

        try:
            # Skriv kod till temporär fil
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False
            ) as f:
                f.write(code)
                script_path = f.name

            logger.info(f"DockerSandbox: Executing code in {self.image}")

            # Kör i Docker med säkerhetsbegränsningar
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "docker", "run", "--rm",
                    "--network=none",              # Ingen internet
                    f"--memory={self.memory_limit}",  # RAM-gräns
                    f"--cpus={self.cpu_limit}",    # CPU-gräns
                    "--read-only",                 # Read-only filesystem
                    "--tmpfs=/tmp:size=64m",       # Tillfällig skrivbar /tmp
                    "-v", f"{script_path}:/sandbox/script.py:ro",
                    self.image,
                    "python", "/sandbox/script.py",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                ),
                timeout=self.timeout
            )

            stdout, stderr = await proc.communicate()
            duration_ms = int((time.time() - start_time) * 1000)

            # Rensa temp-fil
            import os
            os.unlink(script_path)

            if proc.returncode == 0:
                logger.info(f"DockerSandbox: Success ({duration_ms}ms)")
                return {
                    "success": True,
                    "output": stdout.decode()[:10000],  # Max 10KB output
                    "error": "",
                    "duration_ms": duration_ms
                }
            else:
                logger.warning(f"DockerSandbox: Failed with code {proc.returncode}")
                return {
                    "success": False,
                    "output": stdout.decode()[:5000],
                    "error": stderr.decode()[:5000],
                    "duration_ms": duration_ms
                }

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"DockerSandbox: Timeout after {self.timeout}s")
            return {
                "success": False,
                "output": "",
                "error": f"Timeout efter {self.timeout} sekunder",
                "duration_ms": duration_ms
            }
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"DockerSandbox: Error - {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "duration_ms": duration_ms
            }

    async def is_available(self) -> bool:
        """Kolla om Docker och sandbox-image finns"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "image", "inspect", self.image,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False


# Global instances
qwen_agent_provider = QwenAgentProvider()
docker_sandbox = DockerSandbox()


def get_qwen_agent_provider() -> QwenAgentProvider:
    """Dependency injection helper"""
    return qwen_agent_provider


def get_docker_sandbox() -> DockerSandbox:
    """Get Docker sandbox instance"""
    return docker_sandbox
