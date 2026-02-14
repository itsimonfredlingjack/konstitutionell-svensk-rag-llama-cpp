#!/usr/bin/env python3
"""
Validate active documentation against legacy-model references.

This check is intended to run in CI and locally:
    python scripts/check_docs_canonical.py
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

# Terms that must not be presented as current stack in active docs.
LEGACY_TERMS: tuple[str, ...] = ("mistral-nemo", "bge-m3", "gpt-sw3")

# Files intentionally allowed to discuss old/new tradeoffs.
ALLOWED_FILE_NAMES: set[str] = {
    "deep-research-by-claude.md",
    "deep-research-by-chatgpt.md",
    "README_DOCS_AND_RAG_INSTRUCTIONS.md",
}

# Line-level context that marks a reference as historical/migration-only.
HISTORICAL_CONTEXT_MARKERS: tuple[str, ...] = (
    "->",
    "→",
    "from",
    "från",
    "migrat",
    "histor",
    "legacy",
    "deprecated",
    "old",
    "tidigare",
    "gamla",
    "ersatt",
    "replaced",
    "arkiver",
)

TERM_PATTERNS: dict[str, re.Pattern[str]] = {
    "mistral-nemo": re.compile(r"\bmistral[-_\s]?nemo\b", flags=re.IGNORECASE),
    "bge-m3": re.compile(r"\bbge[-_\s]?m3\b", flags=re.IGNORECASE),
    "gpt-sw3": re.compile(r"\bgpt[-_\s]?sw3\b", flags=re.IGNORECASE),
}


@dataclass(frozen=True)
class Violation:
    path: str
    line_number: int
    term: str
    line: str


def _iter_markdown_files(docs_root: Path):
    for path in docs_root.rglob("*.md"):
        relative = path.relative_to(docs_root)
        if "archive" in relative.parts:
            continue
        yield path


def _line_is_historical_context(line: str) -> bool:
    lowered = line.casefold()
    return any(marker in lowered for marker in HISTORICAL_CONTEXT_MARKERS)


def _file_allows_historical_references(path: Path) -> bool:
    return path.name in ALLOWED_FILE_NAMES


def scan_docs(docs_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    docs_root = docs_root.resolve()

    if not docs_root.exists():
        raise FileNotFoundError(f"Docs directory does not exist: {docs_root}")

    for path in _iter_markdown_files(docs_root):
        allow_file = _file_allows_historical_references(path)
        content = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(content.splitlines(), start=1):
            for term in LEGACY_TERMS:
                if not TERM_PATTERNS[term].search(line):
                    continue

                if allow_file or _line_is_historical_context(line):
                    continue

                violations.append(
                    Violation(
                        path=str(path.relative_to(docs_root.parent)),
                        line_number=line_number,
                        term=term,
                        line=line.strip(),
                    )
                )
    return violations


def _build_report(violations: list[Violation]) -> str:
    if not violations:
        return "Docs canonicality check passed: no disallowed legacy references found."

    lines = [
        f"Docs canonicality check failed: {len(violations)} disallowed legacy references found.",
        "",
    ]
    for violation in violations:
        lines.append(
            f"- {violation.path}:{violation.line_number} [{violation.term}] {violation.line}"
        )
    lines.append("")
    lines.append(
        "Allowed contexts: docs/archive/**, deep-research docs, README_DOCS_AND_RAG_INSTRUCTIONS.md, "
        "or explicit historical/migration wording on the same line."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check active docs for legacy model references outside allowed contexts."
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs"),
        help="Path to docs directory (default: docs).",
    )
    args = parser.parse_args()

    violations = scan_docs(args.docs_dir)
    print(_build_report(violations))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
