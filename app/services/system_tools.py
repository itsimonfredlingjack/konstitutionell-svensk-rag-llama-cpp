"""
QWEN SysAdmin Tools
Ger QWEN förmågan att köra systemkommandon säkert.

Säkerhetsnivåer:
- SAFE: Körs direkt (read-only operationer)
- DANGEROUS: Kräver användarbekräftelse (write/restart operationer)
"""

import asyncio
import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from datetime import datetime

from ..utils.logging import get_logger

logger = get_logger(__name__)


class SafetyLevel(Enum):
    """Säkerhetsnivå för verktyg"""
    SAFE = "safe"           # Körs direkt
    DANGEROUS = "dangerous" # Kräver bekräftelse


@dataclass
class ToolDefinition:
    """Definition av ett verktyg"""
    name: str
    description: str
    safety: SafetyLevel
    params: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """Resultat från verktygsexekvering"""
    success: bool
    output: str = ""
    error: str = ""
    tool_name: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "tool_name": self.tool_name,
            "duration_ms": self.duration_ms,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


# ═══════════════════════════════════════════════════════════════════════════════
# VERKTYGS-DEFINITIONER
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS: dict[str, ToolDefinition] = {
    # ═══════════════ DOCKER ═══════════════
    "docker_ps": ToolDefinition(
        name="docker_ps",
        description="Lista alla containers (körande och stoppade)",
        safety=SafetyLevel.SAFE,
        params=[]
    ),
    "docker_logs": ToolDefinition(
        name="docker_logs",
        description="Visa loggar för en container",
        safety=SafetyLevel.SAFE,
        params=["container"]
    ),
    "docker_restart": ToolDefinition(
        name="docker_restart",
        description="Starta om en container",
        safety=SafetyLevel.DANGEROUS,
        params=["container"]
    ),
    "docker_stop": ToolDefinition(
        name="docker_stop",
        description="Stoppa en container",
        safety=SafetyLevel.DANGEROUS,
        params=["container"]
    ),
    "docker_start": ToolDefinition(
        name="docker_start",
        description="Starta en stoppad container",
        safety=SafetyLevel.DANGEROUS,
        params=["container"]
    ),

    # ═══════════════ SYSTEMD ═══════════════
    "service_status": ToolDefinition(
        name="service_status",
        description="Visa status för en systemd-tjänst",
        safety=SafetyLevel.SAFE,
        params=["service"]
    ),
    "service_logs": ToolDefinition(
        name="service_logs",
        description="Visa journalctl-loggar för en tjänst",
        safety=SafetyLevel.SAFE,
        params=["service"]
    ),
    "service_restart": ToolDefinition(
        name="service_restart",
        description="Starta om en systemd-tjänst",
        safety=SafetyLevel.DANGEROUS,
        params=["service"]
    ),
    "service_stop": ToolDefinition(
        name="service_stop",
        description="Stoppa en systemd-tjänst",
        safety=SafetyLevel.DANGEROUS,
        params=["service"]
    ),
    "service_start": ToolDefinition(
        name="service_start",
        description="Starta en systemd-tjänst",
        safety=SafetyLevel.DANGEROUS,
        params=["service"]
    ),

    # ═══════════════ FILES ═══════════════
    "file_read": ToolDefinition(
        name="file_read",
        description="Läs innehållet i en fil (max 10KB)",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),
    "file_write": ToolDefinition(
        name="file_write",
        description="Skriv innehåll till en fil",
        safety=SafetyLevel.DANGEROUS,
        params=["path", "content"]
    ),
    "file_list": ToolDefinition(
        name="file_list",
        description="Lista filer i en katalog",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),
    "file_exists": ToolDefinition(
        name="file_exists",
        description="Kontrollera om en fil eller katalog finns",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),

    # ═══════════════ SYSTEM ═══════════════
    "system_stats": ToolDefinition(
        name="system_stats",
        description="Visa CPU, RAM, Disk och GPU-statistik",
        safety=SafetyLevel.SAFE,
        params=[]
    ),
    "ollama_list": ToolDefinition(
        name="ollama_list",
        description="Lista alla installerade Ollama-modeller",
        safety=SafetyLevel.SAFE,
        params=[]
    ),
    "ollama_ps": ToolDefinition(
        name="ollama_ps",
        description="Visa körande/laddade Ollama-modeller",
        safety=SafetyLevel.SAFE,
        params=[]
    ),
    "shell": ToolDefinition(
        name="shell",
        description="Kör ett godtyckligt shell-kommando",
        safety=SafetyLevel.DANGEROUS,
        params=["command"]
    ),

    # ═══════════════ GIT (Grok tip) ═══════════════
    "git_status": ToolDefinition(
        name="git_status",
        description="Visa git status i en katalog",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),
    "git_diff": ToolDefinition(
        name="git_diff",
        description="Visa git diff (ändringar)",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),
    "git_log": ToolDefinition(
        name="git_log",
        description="Visa senaste commits",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),
    "git_branch": ToolDefinition(
        name="git_branch",
        description="Lista git branches",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),

    # ═══════════════ PYTEST (Grok tip) ═══════════════
    "pytest_run": ToolDefinition(
        name="pytest_run",
        description="Kör pytest i en katalog",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),
    "pytest_coverage": ToolDefinition(
        name="pytest_coverage",
        description="Kör pytest med coverage-rapport",
        safety=SafetyLevel.SAFE,
        params=["path"]
    ),

    # ═══════════════ WEB SEARCH (Grok tip) ═══════════════
    "web_search": ToolDefinition(
        name="web_search",
        description="Sök på webben via DuckDuckGo",
        safety=SafetyLevel.SAFE,
        params=["query"]
    ),
}


def get_tool_definitions() -> dict[str, dict]:
    """Returnera verktygs-definitioner för system prompt"""
    return {
        name: {
            "description": tool.description,
            "safety": tool.safety.value,
            "params": tool.params
        }
        for name, tool in TOOLS.items()
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM TOOLS EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════════

class SystemTools:
    """Executor för QWEN SysAdmin-verktyg"""

    def __init__(self):
        # Tillåtna sökvägar för filoperationer
        self.allowed_paths = [
            "/home/ai-server",
            "/var/log",
            "/etc/nginx",
            "/tmp",
            "/opt"
        ]
        # Max output storlek (bytes)
        self.max_output_size = 10240  # 10KB
        # Timeout för kommandon (sekunder)
        self.timeout = 60

    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """Kör ett verktyg och returnera resultat"""
        import time
        start_time = time.time()

        if tool_name not in TOOLS:
            return ToolResult(
                success=False,
                error=f"Okänt verktyg: {tool_name}",
                tool_name=tool_name
            )

        tool = TOOLS[tool_name]

        # Validera obligatoriska parametrar
        missing = [p for p in tool.params if p not in params and p != "lines"]
        if missing:
            return ToolResult(
                success=False,
                error=f"Saknar obligatoriska parametrar: {', '.join(missing)}",
                tool_name=tool_name
            )

        # Dispatch till rätt metod
        method = getattr(self, f"_exec_{tool_name}", None)
        if not method:
            return ToolResult(
                success=False,
                error=f"Verktyget {tool_name} är inte implementerat",
                tool_name=tool_name
            )

        try:
            result = await asyncio.wait_for(
                method(params),
                timeout=self.timeout
            )
            result.tool_name = tool_name
            result.duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Tool executed: {tool_name} (success={result.success}, {result.duration_ms}ms)")
            return result

        except asyncio.TimeoutError:
            logger.error(f"Tool timeout: {tool_name}")
            return ToolResult(
                success=False,
                error=f"Timeout efter {self.timeout} sekunder",
                tool_name=tool_name,
                duration_ms=int((time.time() - start_time) * 1000)
            )
        except Exception as e:
            logger.error(f"Tool error: {tool_name} - {e}")
            return ToolResult(
                success=False,
                error=str(e),
                tool_name=tool_name,
                duration_ms=int((time.time() - start_time) * 1000)
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # DOCKER VERKTYG
    # ═══════════════════════════════════════════════════════════════════════════

    async def _exec_docker_ps(self, params: dict) -> ToolResult:
        """Lista alla Docker containers"""
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a", "--format",
            "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=stdout.decode()[:self.max_output_size])

    async def _exec_docker_logs(self, params: dict) -> ToolResult:
        """Visa container-loggar"""
        container = params["container"]
        lines = params.get("lines", 50)

        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", str(lines), container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        # Docker skriver ofta loggar till stderr
        output = stdout.decode() + stderr.decode()
        return ToolResult(success=True, output=output[:self.max_output_size])

    async def _exec_docker_restart(self, params: dict) -> ToolResult:
        """Starta om en container"""
        container = params["container"]

        proc = await asyncio.create_subprocess_exec(
            "docker", "restart", container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=f"Container '{container}' har startats om")

    async def _exec_docker_stop(self, params: dict) -> ToolResult:
        """Stoppa en container"""
        container = params["container"]

        proc = await asyncio.create_subprocess_exec(
            "docker", "stop", container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=f"Container '{container}' har stoppats")

    async def _exec_docker_start(self, params: dict) -> ToolResult:
        """Starta en container"""
        container = params["container"]

        proc = await asyncio.create_subprocess_exec(
            "docker", "start", container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=f"Container '{container}' har startats")

    # ═══════════════════════════════════════════════════════════════════════════
    # SYSTEMD VERKTYG
    # ═══════════════════════════════════════════════════════════════════════════

    async def _exec_service_status(self, params: dict) -> ToolResult:
        """Visa status för en systemd-tjänst"""
        service = params["service"]

        proc = await asyncio.create_subprocess_exec(
            "systemctl", "status", service, "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        # systemctl status returnerar non-zero för inaktiva tjänster
        output = stdout.decode() or stderr.decode()
        return ToolResult(success=True, output=output[:self.max_output_size])

    async def _exec_service_logs(self, params: dict) -> ToolResult:
        """Visa journalctl-loggar för en tjänst"""
        service = params["service"]
        lines = params.get("lines", 50)

        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-u", service, "-n", str(lines), "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode() or stderr.decode()
        return ToolResult(success=True, output=output[:self.max_output_size])

    async def _exec_service_restart(self, params: dict) -> ToolResult:
        """Starta om en systemd-tjänst"""
        service = params["service"]

        proc = await asyncio.create_subprocess_exec(
            "sudo", "systemctl", "restart", service,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=f"Tjänsten '{service}' har startats om")

    async def _exec_service_stop(self, params: dict) -> ToolResult:
        """Stoppa en systemd-tjänst"""
        service = params["service"]

        proc = await asyncio.create_subprocess_exec(
            "sudo", "systemctl", "stop", service,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=f"Tjänsten '{service}' har stoppats")

    async def _exec_service_start(self, params: dict) -> ToolResult:
        """Starta en systemd-tjänst"""
        service = params["service"]

        proc = await asyncio.create_subprocess_exec(
            "sudo", "systemctl", "start", service,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=f"Tjänsten '{service}' har startats")

    # ═══════════════════════════════════════════════════════════════════════════
    # FIL VERKTYG
    # ═══════════════════════════════════════════════════════════════════════════

    def _is_allowed_path(self, path: str) -> bool:
        """Kontrollera att sökväg är tillåten"""
        try:
            resolved = Path(path).resolve()
            return any(str(resolved).startswith(p) for p in self.allowed_paths)
        except Exception:
            return False

    async def _exec_file_read(self, params: dict) -> ToolResult:
        """Läs innehållet i en fil"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(
                success=False,
                error=f"Otillåten sökväg: {path}. Tillåtna: {', '.join(self.allowed_paths)}"
            )

        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(success=False, error=f"Filen finns inte: {path}")

            if file_path.is_dir():
                return ToolResult(success=False, error=f"Sökvägen är en katalog, använd file_list istället")

            content = file_path.read_text(encoding='utf-8', errors='replace')
            return ToolResult(success=True, output=content[:self.max_output_size])

        except PermissionError:
            return ToolResult(success=False, error=f"Ingen läsbehörighet för: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _exec_file_write(self, params: dict) -> ToolResult:
        """Skriv innehåll till en fil"""
        path = params["path"]
        content = params["content"]

        if not self._is_allowed_path(path):
            return ToolResult(
                success=False,
                error=f"Otillåten sökväg: {path}. Tillåtna: {', '.join(self.allowed_paths)}"
            )

        try:
            file_path = Path(path)

            # Skapa parent-kataloger om de inte finns
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content, encoding='utf-8')
            return ToolResult(success=True, output=f"Skrev {len(content)} tecken till {path}")

        except PermissionError:
            return ToolResult(success=False, error=f"Ingen skrivbehörighet för: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _exec_file_list(self, params: dict) -> ToolResult:
        """Lista filer i en katalog"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(
                success=False,
                error=f"Otillåten sökväg: {path}. Tillåtna: {', '.join(self.allowed_paths)}"
            )

        try:
            dir_path = Path(path)
            if not dir_path.exists():
                return ToolResult(success=False, error=f"Katalogen finns inte: {path}")

            if not dir_path.is_dir():
                return ToolResult(success=False, error=f"Sökvägen är inte en katalog: {path}")

            entries = []
            for entry in sorted(dir_path.iterdir()):
                entry_type = "D" if entry.is_dir() else "F"
                size = entry.stat().st_size if entry.is_file() else 0
                entries.append(f"[{entry_type}] {entry.name} ({size} bytes)")

            output = f"Innehåll i {path}:\n" + "\n".join(entries[:100])  # Max 100 entries
            return ToolResult(success=True, output=output)

        except PermissionError:
            return ToolResult(success=False, error=f"Ingen läsbehörighet för: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _exec_file_exists(self, params: dict) -> ToolResult:
        """Kontrollera om en fil finns"""
        path = params["path"]

        try:
            file_path = Path(path)
            exists = file_path.exists()
            file_type = "katalog" if file_path.is_dir() else "fil" if file_path.is_file() else "okänd"

            if exists:
                return ToolResult(success=True, output=f"Ja, {path} finns ({file_type})")
            else:
                return ToolResult(success=True, output=f"Nej, {path} finns inte")

        except Exception as e:
            return ToolResult(success=False, error=str(e))

    # ═══════════════════════════════════════════════════════════════════════════
    # SYSTEM VERKTYG
    # ═══════════════════════════════════════════════════════════════════════════

    async def _exec_system_stats(self, params: dict) -> ToolResult:
        """Visa system-statistik"""
        try:
            import psutil

            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()

            # RAM
            mem = psutil.virtual_memory()
            ram_used = mem.used / (1024**3)
            ram_total = mem.total / (1024**3)
            ram_percent = mem.percent

            # Disk
            disk = psutil.disk_usage('/')
            disk_used = disk.used / (1024**3)
            disk_total = disk.total / (1024**3)
            disk_percent = disk.percent

            output = f"""SYSTEM STATS
═══════════════════════════════
CPU:  {cpu_percent:.1f}% ({cpu_count} cores)
RAM:  {ram_used:.1f} / {ram_total:.1f} GB ({ram_percent:.1f}%)
Disk: {disk_used:.1f} / {disk_total:.1f} GB ({disk_percent:.1f}%)
"""

            # GPU (nvidia-smi)
            gpu_proc = await asyncio.create_subprocess_exec(
                "nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            gpu_stdout, _ = await gpu_proc.communicate()

            if gpu_proc.returncode == 0:
                gpu_data = gpu_stdout.decode().strip().split(", ")
                if len(gpu_data) >= 5:
                    output += f"""
GPU:  {gpu_data[0]}
VRAM: {gpu_data[1]} / {gpu_data[2]} MB
Temp: {gpu_data[3]}°C
Util: {gpu_data[4]}%
"""

            return ToolResult(success=True, output=output)

        except ImportError:
            return ToolResult(success=False, error="psutil är inte installerat")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _exec_ollama_list(self, params: dict) -> ToolResult:
        """Lista installerade Ollama-modeller"""
        proc = await asyncio.create_subprocess_exec(
            "ollama", "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=stdout.decode()[:self.max_output_size])

    async def _exec_ollama_ps(self, params: dict) -> ToolResult:
        """Visa körande/laddade Ollama-modeller"""
        proc = await asyncio.create_subprocess_exec(
            "ollama", "ps",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        output = stdout.decode()
        if not output.strip() or "NAME" not in output:
            output = "Inga modeller är laddade just nu"

        return ToolResult(success=True, output=output[:self.max_output_size])

    async def _exec_shell(self, params: dict) -> ToolResult:
        """Kör ett godtyckligt shell-kommando"""
        command = params["command"]

        # Säkerhetskontroll - blockera extremt farliga kommandon
        blocked_patterns = [
            "rm -rf /",
            "rm -rf /*",
            "> /dev/sd",
            "mkfs",
            ":(){ :|:& };:",  # Fork bomb
            "dd if=",
        ]

        for pattern in blocked_patterns:
            if pattern in command:
                return ToolResult(
                    success=False,
                    error=f"Kommandot är blockerat av säkerhetsskäl: {pattern}"
                )

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/home/ai-server"
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode()
        if stderr:
            output += f"\n[STDERR]\n{stderr.decode()}"

        return ToolResult(
            success=proc.returncode == 0,
            output=output[:self.max_output_size],
            error="" if proc.returncode == 0 else f"Exit code: {proc.returncode}"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # GIT VERKTYG (Grok tip)
    # ═══════════════════════════════════════════════════════════════════════════

    async def _exec_git_status(self, params: dict) -> ToolResult:
        """Visa git status"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(success=False, error=f"Otillåten sökväg: {path}")

        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--short", "--branch",
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=stdout.decode()[:self.max_output_size])

    async def _exec_git_diff(self, params: dict) -> ToolResult:
        """Visa git diff"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(success=False, error=f"Otillåten sökväg: {path}")

        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--stat",
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        output = stdout.decode()
        if not output.strip():
            output = "Inga ändringar (clean working tree)"

        return ToolResult(success=True, output=output[:self.max_output_size])

    async def _exec_git_log(self, params: dict) -> ToolResult:
        """Visa senaste commits"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(success=False, error=f"Otillåten sökväg: {path}")

        proc = await asyncio.create_subprocess_exec(
            "git", "log", "--oneline", "-n", "10",
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=stdout.decode()[:self.max_output_size])

    async def _exec_git_branch(self, params: dict) -> ToolResult:
        """Lista git branches"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(success=False, error=f"Otillåten sökväg: {path}")

        proc = await asyncio.create_subprocess_exec(
            "git", "branch", "-a",
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            return ToolResult(success=False, error=stderr.decode()[:500])

        return ToolResult(success=True, output=stdout.decode()[:self.max_output_size])

    # ═══════════════════════════════════════════════════════════════════════════
    # PYTEST VERKTYG (Grok tip)
    # ═══════════════════════════════════════════════════════════════════════════

    async def _exec_pytest_run(self, params: dict) -> ToolResult:
        """Kör pytest i en katalog"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(success=False, error=f"Otillåten sökväg: {path}")

        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest", "-v", "--tb=short",
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode()
        if stderr:
            output += f"\n[STDERR]\n{stderr.decode()}"

        return ToolResult(
            success=proc.returncode == 0,
            output=output[:self.max_output_size],
            error="" if proc.returncode == 0 else "Tester misslyckades"
        )

    async def _exec_pytest_coverage(self, params: dict) -> ToolResult:
        """Kör pytest med coverage"""
        path = params["path"]

        if not self._is_allowed_path(path):
            return ToolResult(success=False, error=f"Otillåten sökväg: {path}")

        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "pytest", "--cov=.", "--cov-report=term-missing",
            cwd=path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        output = stdout.decode()
        if stderr:
            output += f"\n[STDERR]\n{stderr.decode()}"

        return ToolResult(
            success=proc.returncode == 0,
            output=output[:self.max_output_size],
            error="" if proc.returncode == 0 else "Coverage-körning misslyckades"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # WEB SEARCH VERKTYG (Grok tip)
    # ═══════════════════════════════════════════════════════════════════════════

    async def _exec_web_search(self, params: dict) -> ToolResult:
        """Sök på webben via DuckDuckGo"""
        query = params["query"]
        max_results = params.get("max_results", 5)

        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(f"**{r['title']}**\n{r['href']}\n{r['body']}\n")

            if not results:
                return ToolResult(success=True, output=f"Inga resultat för: {query}")

            output = f"Sökresultat för '{query}':\n\n" + "\n---\n".join(results)
            return ToolResult(success=True, output=output[:self.max_output_size])

        except ImportError:
            return ToolResult(
                success=False,
                error="duckduckgo-search är inte installerat. Kör: pip install duckduckgo-search"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Sökfel: {str(e)}")


# Global instans
system_tools = SystemTools()
