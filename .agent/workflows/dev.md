---
description: Development workflow for vibe-cli UI
---

# Development Workflow

## Running the App

// turbo
1. Launch vibe-cli in your terminal:
```bash
./.venv/bin/python3 -m vibe_cli
```

## Hot-Reload Development

**Note:** `textual run --dev` may not work correctly with package-based apps. Use the following approach instead:

// turbo
2. For rapid iteration, run with Python directly:
```bash
./.venv/bin/python3 -c "from vibe_cli.ui.app import VibeApp; VibeApp().run()"
```

## Clearing Asset Cache

If you modify ASCII art assets and want to see changes without restarting:
```python
from vibe_cli.ui.assets.loader import clear_cache
clear_cache()
```

## Testing CSS Changes

The app has a DEFAULT_CSS fallback. If your CSS has errors:
1. The app will still launch with minimal styling
2. Check the console for CSS error messages

## Common Issues

- **"textual run" shows Textual demo**: Use `python -m vibe_cli` instead
- **CSS crashes**: Check for invalid properties like `z-index` (not supported)
- **Assets not loading**: Verify files exist in `vibe_cli/ui/assets/`
