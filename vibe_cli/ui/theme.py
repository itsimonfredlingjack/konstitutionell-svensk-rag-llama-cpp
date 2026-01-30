# vibe_cli/ui/theme.py

from rich.box import ROUNDED

# Pro Dark Palette (Carbon/Monokai inspired)
COLORS = {
    "bg": "#1e1e1e",           # VSCode Dark
    "surface": "#252526",      # Lighter background
    "surface_light": "#333333",
    "surface_glow": "#444444",

    "primary": "#61afef",      # Blue (Info/Structure)
    "secondary": "#98c379",    # Green (Success/Add)
    "tertiary": "#e5c07b",     # Yellow (Warning/Change)
    
    "error": "#e06c75",        # Red
    "warning": "#d19a66",      # Orange
    "success": "#98c379",      # Green

    "text": "#abb2bf",         # Standard Text
    "text_dim": "#5c6370",     # Comments
    "text_bright": "#ffffff",  # Highlights
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

class VibeNeonStyle(PygmentsStyle):
    """Pro Dark Syntax Highlighting"""

    background_color = COLORS["surface"]
    highlight_color = COLORS["surface_light"]

    styles = {
        Keyword: f"bold {COLORS['primary']}",             # Blue
        Keyword.Constant: f"bold {COLORS['tertiary']}",   # Yellow
        Keyword.Namespace: f"bold {COLORS['primary']}",
        
        Name: COLORS["text"],
        Name.Function: f"bold {COLORS['primary']}",       # Blue
        Name.Class: f"bold {COLORS['tertiary']}",         # Yellow
        Name.Builtin: COLORS["primary"],
        
        String: COLORS["secondary"],                      # Green
        String.Doc: f"italic {COLORS['text_dim']}",
        
        Number: COLORS["tertiary"],                       # Yellow
        Operator: COLORS["primary"],
        
        Comment: f"italic {COLORS['text_dim']}",          # Grey
        Error: f"bold {COLORS['error']}",                 # Red
        
        Generic.Prompt: f"bold {COLORS['primary']}",
        Generic.Output: COLORS["text"],
        Generic.Traceback: COLORS["error"],
    }