"""
GPU Panel - Live nvidia-smi stats for Mission Control layout.
"""
import asyncio
from dataclasses import dataclass
from typing import Optional
from rich.panel import Panel
from rich.text import Text
from rich import box


@dataclass
class GPUStats:
    """GPU statistics from nvidia-smi."""
    name: str = "N/A"
    temp: int = 0
    vram_used: float = 0.0
    vram_total: float = 0.0
    gpu_util: int = 0
    power: int = 0
    available: bool = False


async def get_gpu_stats() -> GPUStats:
    """Query nvidia-smi and return GPU stats."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'nvidia-smi',
            '--query-gpu=name,temperature.gpu,memory.used,memory.total,utilization.gpu,power.draw',
            '--format=csv,noheader,nounits',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return GPUStats()

        # Parse: "NVIDIA GeForce RTX 4070, 45, 2100, 12288, 67, 120.5"
        line = stdout.decode().strip()
        parts = [p.strip() for p in line.split(',')]

        if len(parts) >= 6:
            return GPUStats(
                name=parts[0].replace('NVIDIA GeForce ', '').replace('NVIDIA ', ''),
                temp=int(parts[1]),
                vram_used=float(parts[2]) / 1024,  # MB -> GB
                vram_total=float(parts[3]) / 1024,  # MB -> GB
                gpu_util=int(parts[4]),
                power=int(float(parts[5])),
                available=True
            )
    except FileNotFoundError:
        pass
    except Exception:
        pass

    return GPUStats()


def render_gpu_panel(stats: GPUStats) -> Panel:
    """Render GPU stats as a Rich Panel."""
    text = Text()

    if stats.available:
        # GPU Name (truncated)
        name = stats.name[:12] if len(stats.name) > 12 else stats.name
        text.append(f"{name}\n", style="bold cyan")
        text.append("─" * 13 + "\n", style="dim")

        # Temperature with color coding
        temp_style = "green"
        if stats.temp > 70:
            temp_style = "red"
        elif stats.temp > 50:
            temp_style = "yellow"
        text.append("Temp: ", style="dim")
        text.append(f"{stats.temp}°C\n", style=temp_style)

        # VRAM usage with bar
        vram_pct = (stats.vram_used / stats.vram_total * 100) if stats.vram_total > 0 else 0
        vram_style = "green"
        if vram_pct > 80:
            vram_style = "red"
        elif vram_pct > 60:
            vram_style = "yellow"

        text.append("VRAM: ", style="dim")
        text.append(f"{stats.vram_used:.1f}", style=vram_style)
        text.append(f"/{stats.vram_total:.0f}G\n", style="dim")

        # VRAM bar
        bar_width = 10
        filled = int(vram_pct / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        text.append(f"[{bar}]\n", style=vram_style)

        # GPU utilization
        util_style = "green"
        if stats.gpu_util > 80:
            util_style = "yellow"
        text.append("Load: ", style="dim")
        text.append(f"{stats.gpu_util}%\n", style=util_style)

        # Power
        text.append("Power: ", style="dim")
        text.append(f"{stats.power}W\n", style="dim white")

    else:
        text.append("GPU\n", style="bold red")
        text.append("─" * 13 + "\n", style="dim")
        text.append("Not\n", style="dim")
        text.append("Available\n", style="dim red")

    return Panel(
        text,
        title="[bold]GPU[/]",
        title_align="left",
        box=box.ROUNDED,
        style="dim",
        padding=(0, 1),
        width=17
    )


def render_tokens_panel(tokens_per_second: float = 0.0, is_streaming: bool = False) -> Panel:
    """Render tokens/second panel."""
    text = Text()

    if is_streaming and tokens_per_second > 0:
        # Animated bar
        bar_width = 10
        # Scale: 0-100 tok/s = full bar
        filled = min(int(tokens_per_second / 10), bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        style = "cyan" if tokens_per_second > 20 else "yellow"
        text.append(f"{bar}\n", style=style)
        text.append(f"{tokens_per_second:.1f} t/s", style=f"bold {style}")
    else:
        text.append("░" * 10 + "\n", style="dim")
        text.append("Idle", style="dim")

    return Panel(
        text,
        title="[bold]TOKENS[/]",
        title_align="left",
        box=box.ROUNDED,
        style="dim",
        padding=(0, 1),
        width=17
    )


def render_status_panel(status: str = "Ready", connected: bool = False) -> Panel:
    """Render status panel."""
    text = Text()

    # Connection indicator
    if connected:
        text.append("● ", style="bold green")
        text.append("Online\n", style="green")
    else:
        text.append("○ ", style="bold red")
        text.append("Offline\n", style="red")

    # Status message (truncated)
    status_short = status[:10] if len(status) > 10 else status
    text.append(status_short, style="dim")

    return Panel(
        text,
        title="[bold]STATUS[/]",
        title_align="left",
        box=box.ROUNDED,
        style="dim",
        padding=(0, 1),
        width=17
    )


def render_models_panel(models: list = None, active_model: str = None) -> Panel:
    """Render available models panel."""
    text = Text()

    if not models:
        models = ["gpt-oss", "devstral"]

    for model in models[:4]:  # Max 4 models shown
        if model == active_model:
            text.append("◉ ", style="bold cyan")
            text.append(f"{model[:10]}\n", style="bold cyan")
        else:
            text.append("○ ", style="dim")
            text.append(f"{model[:10]}\n", style="dim")

    return Panel(
        text,
        title="[bold]MODELS[/]",
        title_align="left",
        box=box.ROUNDED,
        style="dim",
        padding=(0, 1),
        width=17
    )


def render_history_panel(messages: list = None) -> Panel:
    """Render message history panel."""
    text = Text()

    if not messages:
        text.append("No history", style="dim")
    else:
        # Show last 6 user messages
        user_msgs = [m for m in messages if m.get("role") == "user"][-6:]
        for msg in user_msgs:
            # Truncate message
            preview = msg.get("text", "")[:11]
            if len(msg.get("text", "")) > 11:
                preview += "…"
            text.append("• ", style="dim cyan")
            text.append(f"{preview}\n", style="dim")

    return Panel(
        text,
        title="[bold]HISTORY[/]",
        title_align="left",
        box=box.ROUNDED,
        style="dim",
        padding=(0, 1),
        width=17
    )


def render_commands_panel() -> Panel:
    """Render available commands panel."""
    text = Text()
    text.append("/quit ", style="dim cyan")
    text.append("/clear\n", style="dim cyan")
    text.append("/help", style="dim")

    return Panel(
        text,
        title="[bold]CMD[/]",
        title_align="left",
        box=box.ROUNDED,
        style="dim",
        padding=(0, 1),
        width=17
    )


# === GPU POLLING TASK ===

async def gpu_poll_loop(state, interval: float = 2.0):
    """Background task that updates GPU stats periodically."""
    while getattr(state, 'running', True):
        try:
            state.gpu_stats = await get_gpu_stats()
        except Exception:
            pass
        await asyncio.sleep(interval)
