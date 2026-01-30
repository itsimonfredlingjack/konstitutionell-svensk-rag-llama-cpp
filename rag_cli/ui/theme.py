# rag_cli/ui/theme.py

from rich.box import ROUNDED

# Stone Light Palette (Constitutional web frontend)
COLORS = {
    "bg": "#C4C0BD",           # Stone-350-ish (clearly grey, not white)
    "surface": "#F5F5F4",      # Stone-100 (panels pop against grey bg)
    "surface_light": "#A8A29E", # Stone-400 (visible borders/dividers)
    "surface_glow": "#E7E5E4",  # Stone-200 (highlight, midpoint)

    "primary": "#0F766E",       # Teal-700 (primär accent)
    "secondary": "#B45309",     # Amber-700 (sekundär accent)
    "tertiary": "#0E7490",      # Cyan-700 (system/info)

    "error": "#B91C1C",         # Red-700
    "warning": "#B45309",       # Amber-700
    "success": "#047857",       # Emerald-700

    "text": "#1C1917",          # Stone-900 (primär text)
    "text_dim": "#57534E",      # Stone-600 (darker dim — readable on light)
    "text_bright": "#0C0A09",   # Stone-950 (betonad text)
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