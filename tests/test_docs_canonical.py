from pathlib import Path

from scripts.check_docs_canonical import scan_docs


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_flags_legacy_model_reference_in_active_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    _write(docs_root / "ARCHITECTURE.md", "LLM: Mistral-Nemo is current production model.\n")

    violations = scan_docs(docs_root)

    assert len(violations) == 1
    assert violations[0].term == "mistral-nemo"
    assert violations[0].path.endswith("ARCHITECTURE.md")


def test_ignores_archive_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    _write(docs_root / "archive" / "legacy.md", "Mistral-Nemo BGE-M3 gpt-sw3\n")

    violations = scan_docs(docs_root)

    assert violations == []


def test_ignores_deep_research_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    _write(docs_root / "deep-research-by-claude.md", "Mistral-Nemo was earlier baseline.\n")

    violations = scan_docs(docs_root)

    assert violations == []


def test_allows_explicit_migration_context(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    _write(docs_root / "MIGRATION_2026.md", "LLM: Mistral-Nemo -> Ministral-3-14B\n")

    violations = scan_docs(docs_root)

    assert violations == []


def test_flags_legacy_term_without_migration_context(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    _write(docs_root / "system-overview.md", "Embedding model: bge-m3\n")

    violations = scan_docs(docs_root)

    assert len(violations) == 1
    assert violations[0].term == "bge-m3"
