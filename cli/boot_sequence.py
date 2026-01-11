"""
THE NEURAL IGNITION - Epic Boot Sequence
A 5-second animation simulating the awakening of a digital consciousness.
"""

import asyncio
import random

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.text import Text

# === FRAME DEFINITIONS ===


def generate_void_frame(width: int = 60, height: int = 15) -> Text:
    """Generate a frame of dormant data points in darkness."""
    text = Text()
    random.seed(42)  # Consistent pattern
    for _y in range(height):
        line = ""
        for _x in range(width):
            if random.random() < 0.03:
                line += "·"
            else:
                line += " "
        text.append(line + "\n", style="dim white")
    return text


def generate_spark_frame(width: int = 60, height: int = 15, spark_size: int = 1) -> Text:
    """Generate a frame with the central spark igniting."""
    text = Text()
    center_x, center_y = width // 2, height // 2
    random.seed(42)

    for y in range(height):
        for x in range(width):
            dist = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5

            if dist < spark_size:
                if dist < 0.5:
                    text.append("✦", style="bold bright_white")
                else:
                    text.append("*", style="bright_yellow")
            elif random.random() < 0.03:
                text.append("·", style="dim white")
            else:
                text.append(" ")
        text.append("\n")
    return text


def generate_shockwave_frame(width: int = 60, height: int = 15, radius: float = 0) -> Text:
    """Generate a frame with expanding shockwave."""
    text = Text()
    center_x, center_y = width // 2, height // 2
    random.seed(42)

    for y in range(height):
        for x in range(width):
            dist = ((x - center_x) ** 2 + ((y - center_y) * 2) ** 2) ** 0.5

            # Core spark
            if dist < 1.5:
                text.append("✦", style="bold bright_white")
            # Shockwave ring
            elif abs(dist - radius) < 1.5:
                if random.random() < 0.7:
                    text.append("░", style="bright_cyan")
                else:
                    text.append("▒", style="cyan")
            # Activated points (inside wave)
            elif dist < radius and random.random() < 0.05:
                text.append("●", style="bright_cyan")
            # Dormant points (outside wave)
            elif random.random() < 0.03:
                if dist < radius:
                    text.append("·", style="cyan")
                else:
                    text.append("·", style="dim white")
            else:
                text.append(" ")
        text.append("\n")
    return text


def generate_neural_frame(width: int = 60, height: int = 15, connections: int = 0) -> Text:
    """Generate a frame with neural network forming."""
    text = Text()
    center_x, center_y = width // 2, height // 2
    random.seed(42)

    # Pre-calculate node positions
    nodes = []
    for _ in range(20):
        nx = random.randint(5, width - 5)
        ny = random.randint(2, height - 2)
        nodes.append((nx, ny))

    # Calculate active connections based on progress
    active_nodes = min(len(nodes), connections)

    for y in range(height):
        for x in range(width):
            dist = ((x - center_x) ** 2 + ((y - center_y) * 2) ** 2) ** 0.5
            is_node = False
            is_connection = False

            # Check if this is a node position
            for i, (nx, ny) in enumerate(nodes[:active_nodes]):
                if x == nx and y == ny:
                    is_node = True
                    break
                # Simple connection lines (horizontal/vertical only for ASCII)
                if i < active_nodes - 1:
                    nx2, ny2 = nodes[i + 1]
                    # Horizontal line
                    if y == ny == ny2 and min(nx, nx2) <= x <= max(nx, nx2):
                        is_connection = True
                    # Vertical line
                    if x == nx == nx2 and min(ny, ny2) <= y <= max(ny, ny2):
                        is_connection = True

            # Core
            if dist < 1.5:
                text.append("✦", style="bold bright_white")
            elif is_node:
                text.append("●", style="bold magenta")
            elif is_connection:
                text.append("─", style="blue")
            elif random.random() < 0.02:
                text.append("·", style="dim cyan")
            else:
                text.append(" ")
        text.append("\n")
    return text


def generate_convergence_frame(width: int = 60, height: int = 15, intensity: int = 0) -> Text:
    """Generate the final convergence frame - solid light form."""
    text = Text()
    center_x, center_y = width // 2, height // 2

    # Box dimensions
    box_w, box_h = 30, 7
    box_x = center_x - box_w // 2
    box_y = center_y - box_h // 2

    chars = " ░▒▓█"

    for y in range(height):
        for x in range(width):
            in_box_x = box_x <= x < box_x + box_w
            in_box_y = box_y <= y < box_y + box_h

            if in_box_x and in_box_y:
                # Inside the converging box
                rel_y = y - box_y

                if rel_y == 0 or rel_y == box_h - 1:
                    text.append("═", style="bright_cyan")
                elif rel_y == box_h // 2:
                    # Center text
                    center_text = " NEURAL LINK "
                    text_start = box_x + (box_w - len(center_text)) // 2
                    if text_start <= x < text_start + len(center_text):
                        char_idx = x - text_start
                        if intensity > 3:
                            text.append(center_text[char_idx], style="bold bright_white")
                        else:
                            text.append(chars[min(intensity, len(chars) - 1)], style="cyan")
                    else:
                        idx = min(intensity, len(chars) - 1)
                        text.append(chars[idx], style="bright_cyan")
                else:
                    idx = min(intensity, len(chars) - 1)
                    text.append(chars[idx], style="bright_cyan")
            else:
                text.append(" ")
        text.append("\n")
    return text


def generate_online_frame(width: int = 60, height: int = 15, pulse: bool = False) -> Text:
    """Generate the final ONLINE frame with pulsing effect."""
    text = Text()
    center_x, center_y = width // 2, height // 2

    # Main box
    box_art = [
        "╔════════════════════════════════╗",
        "║  ████████████████████████████  ║",
        "║  ██                        ██  ║",
        "║  ██    N E U R A L   A I   ██  ║",
        "║  ██                        ██  ║",
        "║  ████████████████████████████  ║",
        "╚════════════════════════════════╝",
        "                                  ",
        "        ═══ O N L I N E ═══       ",
    ]

    box_w = len(box_art[0])
    box_x = center_x - box_w // 2
    box_y = center_y - len(box_art) // 2

    style = "bold bright_white" if pulse else "bright_cyan"
    online_style = "bold bright_green" if pulse else "green"

    for y in range(height):
        rel_y = y - box_y
        if 0 <= rel_y < len(box_art):
            line = box_art[rel_y]
            padding = " " * max(0, box_x)

            if rel_y == len(box_art) - 1:
                text.append(padding + line + "\n", style=online_style)
            else:
                text.append(padding + line + "\n", style=style)
        else:
            text.append(" " * width + "\n")

    return text


# === ANIMATION RUNNER ===


async def run_neural_ignition(console: Console) -> None:
    """Run the complete Neural Ignition boot sequence."""

    width, height = 70, 20

    frames = []

    # Phase 1: VOID (0.5s = 5 frames @ 100ms)
    for _ in range(5):
        frames.append((generate_void_frame(width, height), 0.1))

    # Phase 2: SPARK (0.3s = 3 frames)
    for size in [1, 2, 3]:
        frames.append((generate_spark_frame(width, height, size), 0.1))

    # Phase 3: SHOCKWAVE (1.5s = 15 frames)
    for r in range(1, 16):
        radius = r * 2.5
        frames.append((generate_shockwave_frame(width, height, radius), 0.1))

    # Phase 4: NEURAL FORMATION (2s = 20 frames)
    for c in range(1, 21):
        frames.append((generate_neural_frame(width, height, c), 0.1))

    # Phase 5: CONVERGENCE (0.7s = 7 frames)
    for i in range(1, 6):
        frames.append((generate_convergence_frame(width, height, i), 0.14))

    # Phase 6: ONLINE (pulsing, 1s = 6 frames)
    for i in range(6):
        pulse = i % 2 == 0
        frames.append((generate_online_frame(width, height, pulse), 0.15))

    # Run animation
    with Live(console=console, screen=True, refresh_per_second=30) as live:
        for frame, delay in frames:
            live.update(Align.center(frame, vertical="middle"))
            await asyncio.sleep(delay)

    # Brief pause to let it sink in
    await asyncio.sleep(0.3)


# === TEST ===

if __name__ == "__main__":
    console = Console()
    asyncio.run(run_neural_ignition(console))
