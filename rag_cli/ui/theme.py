# rag_cli/ui/theme.py

from pygments.style import Style as PygmentsStyle
from pygments.token import Comment, Error, Generic, Keyword, Name, Number, Operator, String
from rich.box import DOUBLE, ROUNDED

# High-Contrast Professional Palette
COLORS = {
    # Light zones (header, sidebar, input, footer)
    "bg": "#FFFFFF",
    "surface": "#F3F4F6",
    "surface_light": "#E5E7EB",
    "surface_glow": "#F9FAFB",
    # Accents (Teal/Blue based)
    "primary": "#0F766E",
    "secondary": "#0369A1",
    "tertiary": "#4338CA",
    # Status Colors
    "error": "#DC2626",
    "warning": "#D97706",
    "success": "#059669",
    # Text Colors (light zones)
    "text": "#1F2937",
    "text_dim": "#6B7280",
    "text_bright": "#111827",
    # Dark output zone
    "output_bg": "#0B0F14",
    "output_border": "#334155",
    "output_text": "#E5E7EB",
    "output_text_dim": "#9CA3AF",
    "output_primary": "#2DD4BF",
    "output_secondary": "#FBBF24",
    "output_tertiary": "#38BDF8",
    "output_success": "#34D399",
    "output_error": "#F87171",
    # User bubble (inside dark zone)
    "user_bubble_bg": "#1E293B",
    "user_bubble_border": "#94A3B8",
    # Surface A: Sidebar + Header (panel chrome — visibly gray)
    "sidebar_bg": "#D9DCE2",
    "sidebar_border": "#C2C7CF",
    "sidebar_title_bg": "#CDD1D8",
    "sidebar_accent": "#0F766E",
    "sidebar_text": "#1F2937",
    "sidebar_text_dim": "#6B7280",
    "header_bg": "#D9DCE2",
    "header_border": "#C2C7CF",
    # Surface B: Dock / control socket (visibly darker than sidebar)
    "input_bg": "#B8BEC8",
    # Inset frame — thick, two-tone for sunken depth
    "input_border_dark": "#4B5563",
    "input_border_light": "#7B8494",
    # Surface C: Input field fill (own tone — not white, not dock)
    "input_field_bg": "#E8EAEF",
    "input_focus_border": "#0F766E",
    # Prompt gutter (between fill and field)
    "input_gutter_bg": "#D4D7DD",
    "input_gutter_sep": "#9CA3AF",
    "placeholder_text": "#9CA3AF",
    "footer_bg": "#B8BEC8",
    "footer_border": "#A8AEB8",
    "footer_text": "#374151",
    # Legacy aliases (for code_theme compatibility)
    "agent_bg": "#09090b",
    "agent_text": "#E5E7EB",
    "agent_border": "#27272A",
    "terminal_bg": "#0B0F14",
    "terminal_border": "#334155",
    "terminal_text": "#E5E7EB",
    "terminal_text_dim": "#9CA3AF",
    "terminal_primary": "#2DD4BF",
    "terminal_secondary": "#FBBF24",
    "terminal_tertiary": "#38BDF8",
    "terminal_success": "#34D399",
    "terminal_error": "#F87171",
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

    $output_bg: {COLORS["output_bg"]};
    $output_border: {COLORS["output_border"]};
    $output_text: {COLORS["output_text"]};
    $output_text_dim: {COLORS["output_text_dim"]};

    $sidebar_bg: {COLORS["sidebar_bg"]};
    $sidebar_border: {COLORS["sidebar_border"]};
    $sidebar_title_bg: {COLORS["sidebar_title_bg"]};
    $sidebar_accent: {COLORS["sidebar_accent"]};

    $header_bg: {COLORS["header_bg"]};
    $header_border: {COLORS["header_border"]};

    $input_bg: {COLORS["input_bg"]};
    $input_border_dark: {COLORS["input_border_dark"]};
    $input_border_light: {COLORS["input_border_light"]};
    $input_field_bg: {COLORS["input_field_bg"]};
    $input_focus_border: {COLORS["input_focus_border"]};
    $input_gutter_bg: {COLORS["input_gutter_bg"]};
    $input_gutter_sep: {COLORS["input_gutter_sep"]};
    $placeholder_text: {COLORS["placeholder_text"]};

    $footer_bg: {COLORS["footer_bg"]};
    $footer_border: {COLORS["footer_border"]};
    $footer_text: {COLORS["footer_text"]};
"""

# --- STRUCTURAL ASSETS ---

HUD = ROUNDED
HEADER_BOX = DOUBLE

# Sidebar width (chars)
SIDEBAR_WIDTH = 26


class RagNeonStyle(PygmentsStyle):
    """Dark Syntax Highlighting for AI Agent Bubbles"""

    background_color = COLORS["agent_bg"]
    highlight_color = "#27272A"

    styles = {
        Keyword: f"bold {COLORS['terminal_primary']}",
        Keyword.Constant: f"bold {COLORS['terminal_tertiary']}",
        Keyword.Namespace: f"bold {COLORS['terminal_primary']}",
        Name: COLORS["agent_text"],
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
        Generic.Output: COLORS["agent_text"],
        Generic.Traceback: COLORS["terminal_error"],
    }


class RagTerminalStyle(PygmentsStyle):
    """Dark terminal-like Syntax Highlighting for system output blocks."""

    background_color = COLORS["terminal_bg"]
    highlight_color = "#111827"

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
