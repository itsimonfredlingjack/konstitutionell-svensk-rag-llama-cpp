"""
System Monitor - CPU, RAM, Disk statistics
Provides real-time system health metrics for the admin dashboard
"""

import asyncio
import os
import time
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime

import psutil

from .gpu_monitor import gpu_monitor
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Cache settings
CACHE_DURATION_SECONDS = 1.0


@dataclass
class SystemHealth:
    """Complete system health statistics"""
    # CPU
    cpu_percent: float
    cpu_count: int
    load_average: tuple[float, float, float]  # 1, 5, 15 min

    # RAM
    ram_total_gb: float
    ram_used_gb: float
    ram_free_gb: float
    ram_percent: float

    # Disk
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_percent: float

    # System
    uptime_seconds: int
    boot_time: str

    # GPU (from gpu_monitor)
    gpu: Optional[dict] = None

    # Timestamp
    timestamp: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class CachedHealth:
    """Cached system health with timestamp"""
    health: SystemHealth
    cached_at: datetime


class SystemMonitor:
    """
    Monitors system resources: CPU, RAM, Disk.

    Features:
    - Async-friendly with caching
    - Integrates with existing GPU monitor
    - Low overhead polling
    """

    def __init__(self):
        self._cache: Optional[CachedHealth] = None
        self._lock = asyncio.Lock()

    async def get_stats(self, force_refresh: bool = False) -> SystemHealth:
        """
        Get current system health statistics.

        Args:
            force_refresh: Bypass cache and fetch fresh stats

        Returns:
            SystemHealth with current system information
        """
        async with self._lock:
            # Check cache validity
            if not force_refresh and self._cache:
                age = (datetime.utcnow() - self._cache.cached_at).total_seconds()
                if age < CACHE_DURATION_SECONDS:
                    return self._cache.health

            # Fetch fresh stats
            health = await self._fetch_stats()

            # Update cache
            self._cache = CachedHealth(
                health=health,
                cached_at=datetime.utcnow()
            )

            return health

    async def _fetch_stats(self) -> SystemHealth:
        """Fetch current system statistics"""
        try:
            # CPU - use interval=None for non-blocking
            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()

            # Load average (Unix only)
            try:
                load_avg = os.getloadavg()
            except (AttributeError, OSError):
                load_avg = (0.0, 0.0, 0.0)

            # RAM
            ram = psutil.virtual_memory()

            # Disk (root partition)
            disk = psutil.disk_usage('/')

            # Uptime
            boot_time = psutil.boot_time()
            uptime_seconds = int(time.time() - boot_time)
            boot_time_str = datetime.fromtimestamp(boot_time).isoformat()

            # GPU (from existing monitor)
            gpu_stats = await gpu_monitor.get_stats()
            gpu_dict = {
                "name": gpu_stats.name,
                "vram_total_gb": gpu_stats.vram_total_gb,
                "vram_used_gb": gpu_stats.vram_used_gb,
                "vram_free_gb": gpu_stats.vram_free_gb,
                "vram_percent": gpu_stats.vram_percent,
                "temperature_c": gpu_stats.temperature_c,
                "gpu_util_percent": gpu_stats.gpu_util_percent,
                "power_draw_w": gpu_stats.power_draw_w,
                "is_available": gpu_stats.is_available,
            }

            return SystemHealth(
                # CPU
                cpu_percent=round(cpu_percent, 1),
                cpu_count=cpu_count,
                load_average=tuple(round(x, 2) for x in load_avg),

                # RAM
                ram_total_gb=round(ram.total / (1024**3), 2),
                ram_used_gb=round(ram.used / (1024**3), 2),
                ram_free_gb=round(ram.available / (1024**3), 2),
                ram_percent=round(ram.percent, 1),

                # Disk
                disk_total_gb=round(disk.total / (1024**3), 2),
                disk_used_gb=round(disk.used / (1024**3), 2),
                disk_free_gb=round(disk.free / (1024**3), 2),
                disk_percent=round((disk.used / disk.total) * 100, 1),

                # System
                uptime_seconds=uptime_seconds,
                boot_time=boot_time_str,

                # GPU
                gpu=gpu_dict,

                # Timestamp
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

        except Exception as e:
            logger.error(f"Failed to fetch system stats: {e}")
            # Return minimal fallback
            return SystemHealth(
                cpu_percent=0.0,
                cpu_count=0,
                load_average=(0.0, 0.0, 0.0),
                ram_total_gb=0.0,
                ram_used_gb=0.0,
                ram_free_gb=0.0,
                ram_percent=0.0,
                disk_total_gb=0.0,
                disk_used_gb=0.0,
                disk_free_gb=0.0,
                disk_percent=0.0,
                uptime_seconds=0,
                boot_time="",
                gpu=None,
                timestamp=datetime.utcnow().isoformat() + "Z"
            )

    async def get_quick_summary(self) -> dict:
        """Get minimal stats for WebSocket broadcast"""
        stats = await self.get_stats()
        return {
            "cpu_percent": stats.cpu_percent,
            "ram_percent": stats.ram_percent,
            "disk_percent": stats.disk_percent,
            "gpu_util_percent": stats.gpu.get("gpu_util_percent", 0) if stats.gpu else 0,
            "gpu_vram_percent": stats.gpu.get("vram_percent", 0) if stats.gpu else 0,
        }

    def format_uptime(self, seconds: int) -> str:
        """Format uptime as human-readable string"""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "< 1m"


# Global monitor instance
system_monitor = SystemMonitor()


async def get_system_monitor() -> SystemMonitor:
    """Dependency injection helper"""
    return system_monitor
