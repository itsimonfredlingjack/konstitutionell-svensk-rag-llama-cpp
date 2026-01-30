# rag_cli/ui/theme.py

from rich.box import ROUNDED

# Stone Light Palette (Constitutional web frontend)
COLORS = {
    "bg": "#E7E5E4",            # Stone-200 (light canvas)
    "surface": "#FAFAF9",       # Stone-50 (panels)
    "surface_light": "#A8A29E", # Stone-400 (visible borders/dividers)
    "surface_glow": "#F5F5F4",  # Stone-100 (highlight, midpoint)

    "primary": "#0F766E",       # Teal-700 (primär accent)
    "secondary": "#B45309",     # Amber-700 (sekundär accent)
    "tertiary": "#0E7490",      # Cyan-700 (system/info)

    "error": "#B91C1C",         # Red-700
    "warning": "#B45309",       # Amber-700
    "success": "#047857",       # Emerald-700

    "text": "#1C1917",          # Stone-900 (primär text)
    "text_dim": "#57534E",      # Stone-600 (darker dim — readable on light)
    "text_bright": "#0C0A09",   # Stone-950 (betonad text)

    # Terminal / system output (dark, high-contrast)
    "terminal_bg": "#0B0F14",
    "terminal_border": "#334155",  # Slate-700
    "terminal_text": "#E5E7EB",    # Gray-200
    "terminal_text_dim": "#9CA3AF",# Gray-400
    "terminal_primary": "#2DD4BF", # Teal-400
    "terminal_secondary": "#FBBF24",# Amber-400
    "terminal_tertiary": "#38BDF8",# Sky-400
    "terminal_success": "#34D399", # Emerald-400
    "terminal_error": "#F87171",   # Red-400
}

CSS_VARS = f"""
    $bg: {COLORS["bg"]};
    $surface: {COLORS["surface"]};
    $surface_light: {COLORS["surface_light"]};
    $surface_glow: {COLORS["surface_glow"]};

    $primary: {COLORS["primary"]};
    $secondary: {COLORS["secondary"]};
    $tertiary: {COLORS["tertiary"]};

    $error: {COLORS["error"]};
    $warning: {COLORS["warning"]};
    $success: {COLORS["success"]};

    $text: {COLORS["text"]};
    $text_dim: {COLORS["text_dim"]};
    $text_bright: {COLORS["text_bright"]};
"""

# --- STRUCTURAL ASSETS ---

# Standard rounded corners for professional look
HUD = ROUNDED

# --- PYGMENTS STYLE ---

from pygments.style import Style as PygmentsStyle
from pygments.token import Comment, Error, Generic, Keyword, Name, Number, Operator, String

class RagNeonStyle(PygmentsStyle):
    """Stone Light Syntax Highlighting"""

    background_color = COLORS["surface"]
    highlight_color = COLORS["surface_glow"]

    styles = {
        Keyword: f"bold {COLORS['primary']}",             # Blue
        Keyword.Constant: f"bold {COLORS['tertiary']}",   # Yellow
        Keyword.Namespace: f"bold {COLORS['primary']}",
        
        Name: COLORS["text"],
        Name.Function: f"bold {COLORS['primary']}",       # Blue
        Name.Class: f"bold {COLORS['tertiary']}",         # Yellow
        Name.Builtin: COLORS["primary"],
        
        String: COLORS["success"],                        # Emerald
        String.Doc: f"italic {COLORS['text_dim']}",
        
        Number: COLORS["secondary"],                      # Amber
        Operator: COLORS["primary"],
        
        Comment: f"italic {COLORS['text_dim']}",          # Grey
        Error: f"bold {COLORS['error']}",                 # Red
        
        Generic.Prompt: f"bold {COLORS['primary']}",
        Generic.Output: COLORS["text"],
        Generic.Traceback: COLORS["error"],
    }


class RagTerminalStyle(PygmentsStyle):
    """Dark terminal-like Syntax Highlighting for system output blocks."""

    background_color = COLORS["terminal_bg"]
    highlight_color = "#111827"  # Slate-900-ish

    styles = {
        Keyword: f"bold {COLORS['terminal_primary']}",
        Keyword.Constant: f"bold {COLORS['terminal_tertiary']}",
        Keyword.Namespace: f"bold {COLORS['terminal_primary']}",

        Name: COLORS["terminal_text"],
        Name.Function: f"bold {COLORS['terminal_primary']}",
        Name.Class: f"bold {COLORS['terminal_tertiary']}",
        Name.Builtin: COLORS["terminal_primary"],

        String: COLORS["terminal_success"],
        String.Doc: f"italic {COLORS['terminal_text_dim']}",

        Number: COLORS["terminal_secondary"],
        Operator: COLORS["terminal_primary"],

        Comment: f"italic {COLORS['terminal_text_dim']}",
        Error: f"bold {COLORS['terminal_error']}",

        Generic.Prompt: f"bold {COLORS['terminal_primary']}",
        Generic.Output: COLORS["terminal_text"],
        Generic.Traceback: COLORS["terminal_error"],
    }
