"""
GPU Monitor - NVIDIA GPU statistics via nvidia-smi
Provides real-time GPU stats for RTX 4070 monitoring
"""

import asyncio
import subprocess
import re
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from ..models.schemas import GPUStats
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Cache settings
CACHE_DURATION_SECONDS = 1.0  # How long to cache GPU stats


@dataclass
class CachedStats:
    """Cached GPU statistics with timestamp"""
    stats: GPUStats
    timestamp: datetime


class GPUMonitor:
    """
    Monitors NVIDIA GPU statistics using nvidia-smi.

    Features:
    - Async subprocess calls to nvidia-smi
    - Caching to avoid excessive calls
    - Fallback values when GPU unavailable
    """

    def __init__(self):
        self._cache: Optional[CachedStats] = None
        self._lock = asyncio.Lock()
        self._nvidia_smi_available: Optional[bool] = None

    async def _check_nvidia_smi(self) -> bool:
        """Check if nvidia-smi is available"""
        if self._nvidia_smi_available is not None:
            return self._nvidia_smi_available

        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            self._nvidia_smi_available = proc.returncode == 0
        except FileNotFoundError:
            self._nvidia_smi_available = False
        except Exception as e:
            logger.warning(f"nvidia-smi check failed: {e}")
            self._nvidia_smi_available = False

        return self._nvidia_smi_available

    async def _run_nvidia_smi(self, args: list[str]) -> Optional[str]:
        """Run nvidia-smi with arguments and return stdout"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return stdout.decode("utf-8").strip()
            else:
                logger.warning(f"nvidia-smi failed: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"Error running nvidia-smi: {e}")
            return None

    async def get_stats(self, force_refresh: bool = False) -> GPUStats:
        """
        Get current GPU statistics.

        Args:
            force_refresh: Bypass cache and fetch fresh stats

        Returns:
            GPUStats with current GPU information
        """
        async with self._lock:
            # Check cache validity
            if not force_refresh and self._cache:
                age = (datetime.utcnow() - self._cache.timestamp).total_seconds()
                if age < CACHE_DURATION_SECONDS:
                    return self._cache.stats

            # Check if nvidia-smi is available
            if not await self._check_nvidia_smi():
                return self._get_fallback_stats()

            # Fetch fresh stats
            stats = await self._fetch_stats()

            # Update cache
            self._cache = CachedStats(
                stats=stats,
                timestamp=datetime.utcnow()
            )

            return stats

    async def _fetch_stats(self) -> GPUStats:
        """Fetch current GPU stats from nvidia-smi"""
        # Query format: index,name,temp,util,mem_util,mem_total,mem_used,mem_free,power_draw,power_limit,fan
        query = (
            "--query-gpu="
            "index,name,temperature.gpu,utilization.gpu,utilization.memory,"
            "memory.total,memory.used,memory.free,"
            "power.draw,power.limit,fan.speed,"
            "driver_version"
        )

        output = await self._run_nvidia_smi([query, "--format=csv,noheader,nounits"])

        if not output:
            return self._get_fallback_stats()

        try:
            # Parse CSV output
            parts = [p.strip() for p in output.split(",")]

            if len(parts) < 11:
                logger.warning(f"Unexpected nvidia-smi output: {output}")
                return self._get_fallback_stats()

            # Parse values with error handling
            def safe_float(val: str, default: float = 0.0) -> float:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default

            def safe_int(val: str, default: int = 0) -> int:
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return default

            vram_total = safe_float(parts[5]) / 1024  # MiB to GB
            vram_used = safe_float(parts[6]) / 1024
            vram_free = safe_float(parts[7]) / 1024

            stats = GPUStats(
                name=parts[1].strip(),
                vram_total_gb=round(vram_total, 2),
                vram_used_gb=round(vram_used, 2),
                vram_free_gb=round(vram_free, 2),
                vram_percent=round((vram_used / vram_total) * 100, 1) if vram_total > 0 else 0,
                temperature_c=safe_int(parts[2]),
                gpu_util_percent=safe_int(parts[3]),
                memory_util_percent=safe_int(parts[4]),
                power_draw_w=safe_int(parts[8]),
                power_limit_w=safe_int(parts[9]),
                fan_speed_percent=safe_int(parts[10]) if parts[10] != "[N/A]" else None,
                driver_version=parts[11].strip() if len(parts) > 11 else None,
                is_available=True
            )

            return stats

        except Exception as e:
            logger.error(f"Failed to parse nvidia-smi output: {e}")
            return self._get_fallback_stats()

    def _get_fallback_stats(self) -> GPUStats:
        """Return fallback stats when GPU monitoring unavailable"""
        return GPUStats(
            name="NVIDIA GeForce RTX 4070",
            vram_total_gb=12.0,
            vram_used_gb=0.0,
            vram_free_gb=12.0,
            vram_percent=0.0,
            temperature_c=0,
            power_draw_w=0,
            power_limit_w=200,
            gpu_util_percent=0,
            memory_util_percent=0,
            is_available=False
        )

    async def get_cuda_version(self) -> Optional[str]:
        """Get CUDA version from nvidia-smi"""
        output = await self._run_nvidia_smi([])

        if output:
            # Parse CUDA version from standard nvidia-smi output
            match = re.search(r"CUDA Version:\s*(\d+\.\d+)", output)
            if match:
                return match.group(1)

        return None

    async def is_gpu_available(self) -> bool:
        """Check if GPU is available and accessible"""
        return await self._check_nvidia_smi()

    async def get_vram_usage_gb(self) -> float:
        """Quick method to get just VRAM usage"""
        stats = await self.get_stats()
        return stats.vram_used_gb

    async def has_sufficient_vram(self, required_gb: float) -> bool:
        """Check if there's enough free VRAM for a model"""
        stats = await self.get_stats()
        return stats.vram_free_gb >= required_gb


# Global monitor instance
gpu_monitor = GPUMonitor()


async def get_gpu_monitor() -> GPUMonitor:
    """Dependency injection helper"""
    return gpu_monitor
