"""
Tests for BM25 FTS5 Service
============================

Unit tests for the SQLite FTS5-backed BM25 service.
Uses a temporary FTS5 database with known Swedish legal documents.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.bm25_service import BM25Service, _sanitize_fts_query

# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

SAMPLE_DOCS = [
    (
        "rf_2_kap_1",
        "Var och en är gentemot det allmänna tillförsäkrad yttrandefrihet "
        "informationsfrihet mötesfrihet demonstrationsfrihet föreningsfrihet "
        "och religionsfrihet",
    ),
    (
        "tf_1_kap_1",
        "Till främjande av ett fritt meningsutbyte tryckfrihet och en allsidig upplysning "
        "skall varje svensk medborgare ha rätt att i tryckt skrift yttra sina tankar och åsikter",
    ),
    (
        "sfs_1915_218",
        "Anbud om slutande av avtal och svar å sådant anbud vare bindande för den "
        "som avgivit anbudet eller svaret",
    ),
    (
        "gdpr_art_6",
        "Behandling av personuppgifter är laglig om den registrerade har lämnat sitt "
        "samtycke till behandling av sina personuppgifter för ett eller flera specifika ändamål",
    ),
    (
        "skl_2_kap_1",
        "Den som uppsåtligen eller av vårdslöshet vållar personskada eller sakskada "
        "skall ersätta skadan genom skadestånd",
    ),
]


@pytest.fixture
def fts5_db(tmp_path) -> Path:
    """Create a temporary FTS5 database with sample documents."""
    db_path = tmp_path / "test_bm25.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            doc_id UNINDEXED,
            content,
            tokenize='unicode61 remove_diacritics 2',
            detail='column'
        )
    """)
    conn.executemany("INSERT INTO docs_fts(doc_id, content) VALUES (?, ?)", SAMPLE_DOCS)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def bm25_service(fts5_db) -> BM25Service:
    """Create a BM25Service pointing to the test FTS5 database."""
    with patch("app.services.bm25_service.get_compound_splitter") as mock_splitter_fn:
        mock_splitter = MagicMock()
        mock_splitter.is_available.return_value = False
        mock_splitter_fn.return_value = mock_splitter
        service = BM25Service(index_path=str(fts5_db))
    return service


@pytest.fixture
def bm25_service_with_splitting(fts5_db) -> BM25Service:
    """Create a BM25Service with compound splitting enabled."""
    with patch("app.services.bm25_service.get_compound_splitter") as mock_splitter_fn:
        mock_splitter = MagicMock()
        mock_splitter.is_available.return_value = True
        mock_splitter.expand_text.side_effect = lambda q: q  # passthrough
        mock_splitter_fn.return_value = mock_splitter
        service = BM25Service(index_path=str(fts5_db))
    return service


# ═══════════════════════════════════════════════════════════════════════════
# TEST: INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBM25Initialization:
    def test_is_available_when_db_exists(self, bm25_service):
        assert bm25_service.is_available() is True

    def test_is_available_when_db_missing(self, tmp_path):
        with patch("app.services.bm25_service.get_compound_splitter") as mock_fn:
            mock_fn.return_value = MagicMock(is_available=MagicMock(return_value=False))
            service = BM25Service(index_path=str(tmp_path / "nonexistent.db"))
        assert service.is_available() is False

    def test_is_loaded_before_search(self, bm25_service):
        assert bm25_service.is_loaded() is False

    def test_lazy_loading_on_search(self, bm25_service):
        assert bm25_service.is_loaded() is False
        bm25_service.search("yttrandefrihet", k=5)
        assert bm25_service.is_loaded() is True

    def test_get_stats_before_load(self, bm25_service):
        stats = bm25_service.get_stats()
        assert stats["available"] is True
        assert stats["loaded"] is False
        assert stats["doc_count"] == 0
        assert stats["backend"] == "sqlite_fts5"

    def test_get_stats_after_load(self, bm25_service):
        bm25_service.search("test", k=1)
        stats = bm25_service.get_stats()
        assert stats["loaded"] is True
        assert stats["doc_count"] == len(SAMPLE_DOCS)
        assert stats["backend"] == "sqlite_fts5"


# ═══════════════════════════════════════════════════════════════════════════
# TEST: SEARCH
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBM25Search:
    def test_basic_search(self, bm25_service):
        results = bm25_service.search("yttrandefrihet", k=5)
        assert len(results) > 0
        assert results[0]["id"] == "rf_2_kap_1"

    def test_result_format(self, bm25_service):
        results = bm25_service.search("personuppgifter", k=5)
        assert len(results) > 0
        result = results[0]
        assert "id" in result
        assert "score" in result
        assert "source" in result
        assert result["source"] == "bm25"

    def test_return_docs(self, bm25_service):
        results = bm25_service.search("avtal", k=5, return_docs=True)
        assert len(results) > 0
        assert "text" in results[0]
        assert "anbud" in results[0]["text"].lower()

    def test_return_docs_false(self, bm25_service):
        results = bm25_service.search("avtal", k=5, return_docs=False)
        assert len(results) > 0
        assert "text" not in results[0]

    def test_empty_query(self, bm25_service):
        assert bm25_service.search("", k=5) == []
        assert bm25_service.search("   ", k=5) == []

    def test_no_match(self, bm25_service):
        results = bm25_service.search("xyznonexistentterm123", k=5)
        assert results == []

    def test_k_limit(self, bm25_service):
        results = bm25_service.search("den", k=2)
        assert len(results) <= 2

    def test_score_ordering(self, bm25_service):
        results = bm25_service.search("personuppgifter behandling", k=10)
        if len(results) >= 2:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_scores_are_positive(self, bm25_service):
        results = bm25_service.search("yttrandefrihet", k=5)
        for r in results:
            assert r["score"] > 0

    def test_search_when_unavailable(self, tmp_path):
        with patch("app.services.bm25_service.get_compound_splitter") as mock_fn:
            mock_fn.return_value = MagicMock(is_available=MagicMock(return_value=False))
            service = BM25Service(index_path=str(tmp_path / "nonexistent.db"))
        results = service.search("anything", k=5)
        assert results == []

    def test_compound_splitting_called(self, bm25_service_with_splitting):
        bm25_service_with_splitting.search("skadeståndsanspråk", k=5)
        bm25_service_with_splitting._compound_splitter.expand_text.assert_called()


# ═══════════════════════════════════════════════════════════════════════════
# TEST: DOC SCORES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBM25DocScores:
    def test_matching_ids(self, bm25_service):
        scores = bm25_service.get_doc_scores("personuppgifter", ["gdpr_art_6", "rf_2_kap_1"])
        assert "gdpr_art_6" in scores
        assert scores["gdpr_art_6"] > 0

    def test_empty_ids(self, bm25_service):
        scores = bm25_service.get_doc_scores("test", [])
        assert scores == {}

    def test_no_match_ids(self, bm25_service):
        scores = bm25_service.get_doc_scores("xyznonexistent", ["gdpr_art_6"])
        assert scores == {} or all(v == 0 for v in scores.values())

    def test_empty_query(self, bm25_service):
        scores = bm25_service.get_doc_scores("", ["gdpr_art_6"])
        assert scores == {}


# ═══════════════════════════════════════════════════════════════════════════
# TEST: FTS QUERY SANITIZATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFTSSanitization:
    def test_basic_query(self):
        result = _sanitize_fts_query("hello world")
        assert '"hello"' in result
        assert '"world"' in result
        assert "OR" in result

    def test_strips_operators(self):
        result = _sanitize_fts_query("hello AND world NOT bad")
        assert "AND" not in result.replace('"AND"', "")
        assert "NOT" not in result.replace('"NOT"', "")
        assert '"hello"' in result
        assert '"world"' in result

    def test_strips_special_chars(self):
        result = _sanitize_fts_query('hello "world" (test) *star*')
        assert '"' not in result.replace('"hello"', "").replace('"world"', "").replace(
            '"test"', ""
        ).replace('"star"', "").replace(" OR ", "")

    def test_empty_input(self):
        assert _sanitize_fts_query("") == ""
        assert _sanitize_fts_query("   ") == ""

    def test_only_operators(self):
        assert _sanitize_fts_query("AND OR NOT") == ""

    def test_swedish_text(self):
        result = _sanitize_fts_query("tryckfrihetsförordningen kapitel")
        assert '"tryckfrihetsförordningen"' in result
        assert '"kapitel"' in result


# ═══════════════════════════════════════════════════════════════════════════
# TEST: LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBM25Lifecycle:
    def test_unload_closes_connection(self, bm25_service):
        bm25_service.search("test", k=1)
        assert bm25_service.is_loaded() is True
        bm25_service.unload()
        assert bm25_service.is_loaded() is False
        assert bm25_service._conn is None

    def test_reload_after_unload(self, bm25_service):
        bm25_service.search("test", k=1)
        bm25_service.unload()
        results = bm25_service.search("yttrandefrihet", k=5)
        assert len(results) > 0
        assert bm25_service.is_loaded() is True

    def test_index_path_property(self, bm25_service, fts5_db):
        assert bm25_service.index_path == fts5_db

    def test_doc_count_after_load(self, bm25_service):
        bm25_service.search("test", k=1)
        assert bm25_service._doc_count == len(SAMPLE_DOCS)

    def test_doc_count_reset_on_unload(self, bm25_service):
        bm25_service.search("test", k=1)
        bm25_service.unload()
        assert bm25_service._doc_count == 0
