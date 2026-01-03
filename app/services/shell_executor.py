"""
Shell Executor - Execute shell commands from mobile app
Designed for LAN-only use with confirmation for dangerous operations
"""

import asyncio
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Maximum output size (10KB)
MAX_OUTPUT_SIZE = 10000
MAX_STDERR_SIZE = 1000

# Command timeout (60 seconds)
DEFAULT_TIMEOUT = 60


@dataclass
class ShellResult:
    """Result from shell command execution"""
    success: bool
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    requires_confirmation: bool = False
    message: Optional[str] = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "requires_confirmation": self.requires_confirmation,
            "message": self.message,
            "timestamp": self.timestamp,
        }


class ShellExecutor:
    """
    Execute shell commands with safety checks.

    Security model: Trust LAN, require confirmation for dangerous commands.
    This is NOT secure for public internet - only use on local network.
    """

    # Patterns that require user confirmation before execution
    DANGEROUS_PATTERNS = [
        "restart",
        "stop",
        "kill",
        "rm ",
        "rm\t",
        "reboot",
        "shutdown",
        "systemctl",
        "service ",
        "pkill",
        "killall",
        "dd ",
        "mkfs",
        "> /",  # redirect to root
    ]

    # Commands that are always blocked (even with confirmation)
    BLOCKED_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        ":(){ :|:& };:",  # fork bomb
        "> /dev/sda",
        "mkfs /dev/sd",
    ]

    def __init__(self):
        self._execution_count = 0

    def _is_dangerous(self, command: str) -> bool:
        """Check if command requires confirmation"""
        cmd_lower = command.lower()
        return any(pattern in cmd_lower for pattern in self.DANGEROUS_PATTERNS)

    def _is_blocked(self, command: str) -> bool:
        """Check if command is always blocked"""
        cmd_lower = command.lower().replace("  ", " ")
        return any(pattern in cmd_lower for pattern in self.BLOCKED_PATTERNS)

    async def execute(
        self,
        command: str,
        confirmed: bool = False,
        timeout: int = DEFAULT_TIMEOUT
    ) -> ShellResult:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute
            confirmed: Whether user has confirmed dangerous commands
            timeout: Timeout in seconds

        Returns:
            ShellResult with output and status
        """
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Strip the $ prefix if present
        if command.startswith("$ "):
            command = command[2:]
        elif command.startswith("$"):
            command = command[1:]

        command = command.strip()

        if not command:
            return ShellResult(
                success=False,
                command=command,
                stdout="",
                stderr="No command provided",
                exit_code=-1,
                duration_ms=0,
                message="Empty command",
                timestamp=timestamp,
            )

        # Check if blocked
        if self._is_blocked(command):
            logger.warning(f"Blocked dangerous command: {command}")
            return ShellResult(
                success=False,
                command=command,
                stdout="",
                stderr="This command is blocked for safety reasons",
                exit_code=-1,
                duration_ms=0,
                message="Command blocked",
                timestamp=timestamp,
            )

        # Check if dangerous and needs confirmation
        if self._is_dangerous(command) and not confirmed:
            logger.info(f"Dangerous command requires confirmation: {command}")
            return ShellResult(
                success=False,
                command=command,
                stdout="",
                stderr="",
                exit_code=0,
                duration_ms=0,
                requires_confirmation=True,
                message=f"Kommandot '{command}' kräver bekräftelse",
                timestamp=timestamp,
            )

        # Execute the command
        logger.info(f"Executing shell command: {command}")
        self._execution_count += 1
        start_time = asyncio.get_event_loop().time()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/home/ai-server"  # Default working directory
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ShellResult(
                    success=False,
                    command=command,
                    stdout="",
                    stderr=f"Command timed out after {timeout} seconds",
                    exit_code=-1,
                    duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                    message="Timeout",
                    timestamp=timestamp,
                )

            duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

            # Decode and truncate output
            stdout_str = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
            stderr_str = stderr.decode("utf-8", errors="replace")[:MAX_STDERR_SIZE]

            success = proc.returncode == 0

            logger.info(f"Command completed: exit_code={proc.returncode}, duration={duration_ms}ms")

            return ShellResult(
                success=success,
                command=command,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
                message="OK" if success else "Command failed",
                timestamp=timestamp,
            )

        except Exception as e:
            logger.error(f"Shell execution error: {e}")
            return ShellResult(
                success=False,
                command=command,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                message=f"Error: {str(e)}",
                timestamp=timestamp,
            )

    async def get_quick_commands(self) -> list[dict]:
        """Return list of quick commands for the UI"""
        return [
            {"id": "uptime", "command": "uptime", "description": "Visa systemupptid", "dangerous": False},
            {"id": "free", "command": "free -h", "description": "Visa minnesanvändning", "dangerous": False},
            {"id": "df", "command": "df -h", "description": "Visa diskutrymme", "dangerous": False},
            {"id": "ps", "command": "ps aux --sort=-%cpu | head -10", "description": "Topp 10 processer (CPU)", "dangerous": False},
            {"id": "nvidia", "command": "nvidia-smi", "description": "GPU-status", "dangerous": False},
            {"id": "ollama_list", "command": "ollama list", "description": "Visa Ollama-modeller", "dangerous": False},
            {"id": "ollama_ps", "command": "ollama ps", "description": "Visa körande modeller", "dangerous": False},
            {"id": "backend_logs", "command": "journalctl -u simons-ai-backend -n 30 --no-pager", "description": "Backend-loggar (30 rader)", "dangerous": False},
            {"id": "frontend_logs", "command": "journalctl -u simons-ai-frontend -n 30 --no-pager", "description": "Frontend-loggar (30 rader)", "dangerous": False},
            {"id": "restart_backend", "command": "sudo systemctl restart simons-ai-backend", "description": "Starta om backend", "dangerous": True},
            {"id": "restart_frontend", "command": "sudo systemctl restart simons-ai-frontend", "description": "Starta om frontend", "dangerous": True},
        ]

    @property
    def execution_count(self) -> int:
        """Number of commands executed this session"""
        return self._execution_count


# Global executor instance
shell_executor = ShellExecutor()


async def get_shell_executor() -> ShellExecutor:
    """Dependency injection helper"""
    return shell_executor
