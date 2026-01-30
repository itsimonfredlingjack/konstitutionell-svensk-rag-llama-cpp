import sys

from vibe_cli.ui.app import VibeApp


def main():
    app = VibeApp()
    app.run()
    return 0

if __name__ == "__main__":
    sys.exit(main())
