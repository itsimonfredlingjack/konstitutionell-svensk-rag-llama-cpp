import sys

from rag_cli.ui.app import RagApp


def main():
    app = RagApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
