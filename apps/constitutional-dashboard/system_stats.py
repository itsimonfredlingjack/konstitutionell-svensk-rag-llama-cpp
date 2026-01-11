from __future__ import annotations

import os
import socket
import subprocess
from datetime import datetime, timezone
from typing import Any


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _try_import_psutil():
    try:
        import psutil  # type: ignore

        return psutil
    except Exception:
        return None


def _bytes_to_gib(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / (1024**3), 2)


def _get_vram_used_gb() -> float | None:
    """Get VRAM usage in GB from nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            # Parse "1234" (MB) -> GB
            mb = float(result.stdout.strip().split()[0])
            return round(mb / 1024.0, 2)
    except Exception:
        pass
    return None


def _get_tps_current() -> float | None:
    """
    Get current TPS (tokens per second) from last LLM call in logs/llama_server.log.
    Reads the last 10 lines and searches for "tokens/s" pattern.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(current_dir))
    log_file = os.path.join(repo_root, "logs", "llama_server.log")

    if not os.path.exists(log_file):
        return None

    try:
        import re

        # Read last 10 lines of log file
        with open(log_file, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            # Search backwards through last 10 lines
            for line in reversed(lines[-10:]):
                # Look for patterns like "45.2 tokens/s" or "tokens/s: 45.2" or "45.2tokens/s"
                # Try multiple patterns
                patterns = [
                    r"(\d+\.?\d*)\s*tokens/s",
                    r"tokens/s[:\s]+(\d+\.?\d*)",
                    r"(\d+\.?\d*)tokens/s",
                ]
                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        try:
                            tps = float(match.group(1))
                            return round(tps, 1)
                        except (ValueError, IndexError):
                            continue
    except Exception:
        pass

    return None


def _get_context_usage_percent() -> float | None:
    """
    Estimate context window usage percentage (0-100) based on token count vs 16k window.
    Reads from logs/backend.log or logs/llama_server.log to find token count.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(current_dir))

    # Try backend.log first, then llama_server.log
    log_files = [
        os.path.join(repo_root, "logs", "backend.log"),
        os.path.join(repo_root, "logs", "llama_server.log"),
    ]

    for log_file in log_files:
        if not os.path.exists(log_file):
            continue

        try:
            import re

            # Read last 20 lines to find token count
            with open(log_file, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                # Search backwards for token count patterns
                for line in reversed(lines[-20:]):
                    # Look for patterns like "tokens: 1234", "token_count: 1234", "prompt_tokens: 1234"
                    patterns = [
                        r"(?:prompt_|input_)?tokens?[:\s=]+(\d+)",
                        r"context[:\s=]+(\d+)\s*tokens?",
                        r"(\d+)\s*tokens?\s*(?:in|used)",
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            try:
                                tokens = int(match.group(1))
                                # Calculate percentage: (tokens / 16384) * 100
                                percent = (tokens / 16384.0) * 100.0
                                return round(min(100.0, max(0.0, percent)), 1)
                            except (ValueError, IndexError):
                                continue
        except Exception:
            continue

    return None


def _read_rag_status() -> str | None:
    """
    Read RAG backend status from /tmp/rag_status.txt.
    Returns: "searching", "thinking", "generating", "idle", or None if file doesn't exist.
    """
    status_file = "/tmp/rag_status.txt"
    try:
        if os.path.exists(status_file):
            with open(status_file, encoding="utf-8") as f:
                status = f.read().strip().upper()
                # Normalize status values
                if status in ("SEARCHING", "SEARCH"):
                    return "searching"
                elif status in ("THINKING", "THINK"):
                    return "thinking"
                elif status in ("GENERATING", "GENERATE"):
                    return "generating"
                elif status in ("IDLE", "READY"):
                    return "idle"
                # Fallback: return lowercase if unknown
                return status.lower() if status else None
    except Exception:
        pass
    return None


def _get_system_status_state() -> str:
    """
    Determine system status: "idle", "searching", "generating", or "offline".
    Reads from /tmp/rag_status.txt if available, otherwise checks backend health.
    """
    # First, try to read status from RAG backend status file
    rag_status = _read_rag_status()
    if rag_status:
        # Map thinking -> searching for dashboard display
        if rag_status == "thinking":
            return "searching"
        return rag_status

    # Fallback: Check if backend is responding (port 8900)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        result = s.connect_ex(("localhost", 8900))
        s.close()
        if result == 0:
            # Backend is up but no status file, assume idle
            return "idle"
    except Exception:
        pass
    return "offline"


def _load_meminfo() -> dict[str, int]:
    info: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                rest = parts[1].strip().split()
                if not rest:
                    continue
                # meminfo reports kB
                try:
                    info[key] = int(rest[0]) * 1024
                except ValueError:
                    continue
    except Exception:
        pass
    return info


def _read_uptime_seconds() -> float | None:
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


def _get_primary_ip() -> str | None:
    # Best-effort: connect UDP socket to a public IP without sending data.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return None


def _get_recent_logs(count: int = 3) -> list[str]:
    """
    Get recent log lines from logs/backend.log, filtering out debug messages.
    Returns list of log lines (most recent first).
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(current_dir))
    log_file = os.path.join(repo_root, "logs", "backend.log")

    if not os.path.exists(log_file):
        return []

    try:
        import re

        # Patterns to filter out debug/trace messages
        debug_patterns = [
            r"DEBUG",
            r"TRACE",
            r"\[DEBUG\]",
            r"\[TRACE\]",
            r"level=DEBUG",
            r"level=TRACE",
        ]

        with open(log_file, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            # Filter out debug lines and empty lines
            filtered_lines = []
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                # Skip debug lines
                is_debug = any(
                    re.search(pattern, line, re.IGNORECASE) for pattern in debug_patterns
                )
                if not is_debug:
                    filtered_lines.append(line)
                    if len(filtered_lines) >= count:
                        break

            # Return in reverse order (most recent first)
            return list(reversed(filtered_lines))
    except Exception:
        pass

    return []


def get_system_status() -> dict[str, Any]:
    """
    Return lightweight CPU/RAM status for the top HUD bar.
    Never throws; always returns a dict.
    """
    psutil = _try_import_psutil()

    hostname = None
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = None

    ip = _get_primary_ip()

    cpu_percent: float | None = None
    cpu_cores: int | None = None
    load_1m: float | None = None
    try:
        load_1m = os.getloadavg()[0]
    except Exception:
        load_1m = None

    mem_total: int | None = None
    mem_used: int | None = None
    mem_available: int | None = None
    mem_percent: float | None = None

    uptime_s = _read_uptime_seconds()

    if psutil is not None:
        try:
            cpu_percent = float(psutil.cpu_percent(interval=0.1))
        except Exception:
            cpu_percent = None
        try:
            cpu_cores = int(psutil.cpu_count() or 0) or None
        except Exception:
            cpu_cores = None
        try:
            vm = psutil.virtual_memory()
            mem_total = int(vm.total)
            mem_used = int(vm.used)
            mem_available = int(vm.available)
            mem_percent = float(vm.percent)
        except Exception:
            pass
    else:
        meminfo = _load_meminfo()
        mem_total = meminfo.get("MemTotal")
        mem_available = meminfo.get("MemAvailable")
        if mem_total is not None and mem_available is not None:
            mem_used = mem_total - mem_available
            mem_percent = round((mem_used / mem_total) * 100, 1) if mem_total else None

    vram_used_gb = _get_vram_used_gb()
    tps_current = _get_tps_current()
    context_usage = _get_context_usage_percent()
    status = _get_system_status_state()
    logs = _get_recent_logs(count=3)

    return {
        "ts": _iso_now(),
        "hostname": hostname,
        "ip": ip,
        "uptime_s": uptime_s,
        "cpu": {
            "percent": cpu_percent,
            "cores": cpu_cores,
            "load_1m": load_1m,
        },
        "memory": {
            "total_bytes": mem_total,
            "used_bytes": mem_used,
            "available_bytes": mem_available,
            "percent": mem_percent,
            "total_gib": _bytes_to_gib(mem_total),
            "used_gib": _bytes_to_gib(mem_used),
        },
        "vram_used": vram_used_gb,
        "tps_current": tps_current,
        "context_usage": context_usage,
        "status": status,
        "logs": logs,
    }
