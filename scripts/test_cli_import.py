import sys
import os

# Add repo root to path
sys.path.append(os.getcwd())

try:
    from cli import main
    print("Successfully imported cli.main")
except ImportError as e:
    print(f"Failed to import cli.main: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error during import: {e}")
    sys.exit(1)
