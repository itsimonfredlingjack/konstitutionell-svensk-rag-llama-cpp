# vibe_cli/ui/assets/loader.py
"""ASCII Art Asset Loader"""

import logging
from pathlib import Path
from typing import Optional

ASSETS_DIR = Path(__file__).parent

_cache: dict[str, str] = {}

def load_ascii_asset(name: str) -> Optional[str]:
    """
    Load an ASCII art asset from the assets directory.
    
    Args:
        name: Asset filename without extension (e.g., 'core_idle')
        
    Returns:
        The content of the asset file, or None if not found.
    """
    if name in _cache:
        return _cache[name]
    
    asset_path = ASSETS_DIR / f"{name}.txt"
    
    if not asset_path.exists():
        logging.warning(f"ASCII asset not found: {asset_path}")
        return None
    
    try:
        content = asset_path.read_text(encoding="utf-8")
        _cache[name] = content
        return content
    except Exception as e:
        logging.error(f"Failed to load ASCII asset {name}: {e}")
        return None

def clear_cache() -> None:
    """Clear the asset cache (useful for hot-reload)."""
    _cache.clear()
