from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class SystemSnapshot:
    cpu: float
    ram: float
    disk: float
    net_up_bps: float
    net_down_bps: float
    vram_used_mb: float | None
    vram_total_mb: float | None


class SystemMetricsProvider:
    def __init__(self) -> None:
        self._last_net = psutil.net_io_counters()
        self._last_time = time.monotonic()

    async def sample(self) -> SystemSnapshot:
        cpu = await asyncio.to_thread(psutil.cpu_percent, interval=None)
        mem = await asyncio.to_thread(psutil.virtual_memory)
        disk = await asyncio.to_thread(psutil.disk_usage, "/")
        net = await asyncio.to_thread(psutil.net_io_counters)

        now = time.monotonic()
        elapsed = max(now - self._last_time, 0.001)
        net_up_bps = (net.bytes_sent - self._last_net.bytes_sent) / elapsed
        net_down_bps = (net.bytes_recv - self._last_net.bytes_recv) / elapsed
        self._last_net = net
        self._last_time = now

        vram_used_mb, vram_total_mb = await asyncio.to_thread(_read_vram)

        return SystemSnapshot(
            cpu=cpu,
            ram=mem.percent,
            disk=disk.percent,
            net_up_bps=net_up_bps,
            net_down_bps=net_down_bps,
            vram_used_mb=vram_used_mb,
            vram_total_mb=vram_total_mb,
        )


def _read_vram() -> tuple[float | None, float | None]:
    try:
        import pynvml
    except Exception:
        return None, None

    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        used_mb = info.used / (1024 * 1024)
        total_mb = info.total / (1024 * 1024)
        return used_mb, total_mb
    except Exception:
        return None, None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
