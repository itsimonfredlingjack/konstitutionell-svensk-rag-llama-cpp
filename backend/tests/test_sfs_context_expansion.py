"""
Tests for SFS context expansion and prompt annotation features.

Tests cover:
- _expand_sfs_context: sibling fetching and snippet expansion
- _format_sfs_annotations: cross-ref, stycke, amendment formatting in prompts
- Graceful degradation when metadata/siblings are missing
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.prompt_service import _format_sfs_annotations, build_llm_context
from app.services.retrieval_orchestrator import RetrievalOrchestrator, SearchResult


# ── Helpers ──────────────────────────────────────────────────────────


def _make_search_result(
    doc_id="sfs_1974_152_1kap_1§_abc123",
    title="RF 1 kap. 1 §",
    snippet="All offentlig makt i Sverige utgår från folket.",
    score=0.85,
    doc_type="sfs",
    source="sfs_lagtext_jina_v3_1024",
    metadata=None,
):
    result = SearchResult(
        id=doc_id,
        title=title,
        snippet=snippet,
        score=score,
        source=source,
        doc_type=doc_type,
    )
    if metadata:
        result._metadata = metadata
    return result


# ── _format_sfs_annotations tests ───────────────────────────────────


def test_format_sfs_annotations_stycke_count():
    """Stycke count > 1 should produce annotation."""
    source = _make_search_result(metadata={"stycke_count": 3})
    result = _format_sfs_annotations(source)
    assert "3 stycken" in result


def test_format_sfs_annotations_single_stycke():
    """Stycke count == 1 should produce no annotation."""
    source = _make_search_result(metadata={"stycke_count": 1})
    result = _format_sfs_annotations(source)
    assert "stycken" not in result


def test_format_sfs_annotations_cross_refs():
    """Cross-references should produce 'Se även' annotation."""
    refs = [
        {"ref_type": "internal", "raw_text": "30 kap. 1 §"},
        {"ref_type": "external", "raw_text": "lagen (2009:400)"},
    ]
    source = _make_search_result(metadata={"cross_refs_json": json.dumps(refs)})
    result = _format_sfs_annotations(source)
    assert "Se även" in result
    assert "30 kap. 1 §" in result
    assert "lagen (2009:400)" in result


def test_format_sfs_annotations_amendment():
    """Amendment ref should produce 'Senast ändrad' annotation."""
    source = _make_search_result(metadata={"amendment_ref": "Lag (2010:1408)"})
    result = _format_sfs_annotations(source)
    assert "Senast ändrad" in result
    assert "2010:1408" in result


def test_format_sfs_annotations_no_metadata():
    """No metadata should return empty string."""
    source = _make_search_result()
    result = _format_sfs_annotations(source)
    assert result == ""


def test_format_sfs_annotations_empty_cross_refs():
    """Empty cross_refs_json should not produce annotation."""
    source = _make_search_result(metadata={"cross_refs_json": ""})
    result = _format_sfs_annotations(source)
    assert "Se även" not in result


def test_format_sfs_annotations_invalid_json():
    """Invalid JSON in cross_refs_json should not crash."""
    source = _make_search_result(metadata={"cross_refs_json": "not valid json"})
    result = _format_sfs_annotations(source)
    assert "Se även" not in result


# ── build_llm_context tests ──────────────────────────────────────────


def test_build_llm_context_sfs_priority_marker():
    """SFS sources should get priority marker."""
    sources = [_make_search_result()]
    context = build_llm_context(sources)
    assert "PRIORITET (SFS)" in context


def test_build_llm_context_non_sfs():
    """Non-SFS sources should not have SFS annotations."""
    source = _make_search_result(doc_type="riksdag")
    context = build_llm_context([source])
    assert "PRIORITET (SFS)" not in context
    assert "Typ: RIKSDAG" in context


def test_build_llm_context_with_sfs_annotations():
    """SFS source with metadata should include annotations."""
    source = _make_search_result(
        metadata={
            "stycke_count": 3,
            "amendment_ref": "Lag (2018:1800)",
        }
    )
    context = build_llm_context([source])
    assert "3 stycken" in context
    assert "Senast ändrad" in context


def test_build_llm_context_empty():
    """No sources should return default message."""
    context = build_llm_context([])
    assert "Inga relevanta" in context


# ── _expand_sfs_context tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_expand_sfs_context_non_sfs_passthrough():
    """Non-SFS results should pass through unchanged."""
    orchestrator = MagicMock(spec=RetrievalOrchestrator)
    orchestrator.client = MagicMock()

    result = _make_search_result(doc_type="riksdag")
    original_snippet = result.snippet

    # Call the unbound method directly
    expanded = await RetrievalOrchestrator._expand_sfs_context(orchestrator, [result])

    assert len(expanded) == 1
    assert expanded[0].snippet == original_snippet


@pytest.mark.asyncio
async def test_expand_sfs_context_no_collection():
    """Missing SFS collection should return results unchanged."""
    orchestrator = MagicMock(spec=RetrievalOrchestrator)
    orchestrator.client = MagicMock()

    result = _make_search_result()
    original_snippet = result.snippet

    with patch(
        "app.services.retrieval_orchestrator._get_collection_with_fallback",
        return_value=None,
    ):
        expanded = await RetrievalOrchestrator._expand_sfs_context(orchestrator, [result])

    assert len(expanded) == 1
    assert expanded[0].snippet == original_snippet


@pytest.mark.asyncio
async def test_expand_sfs_context_with_siblings():
    """SFS results with sibling IDs should get expanded snippets."""
    mock_collection = MagicMock()

    # First call: fetch metadata for the SFS result
    mock_collection.get.side_effect = [
        # First call: get metadata for main result
        {
            "ids": ["sfs_1974_152_1kap_1§_abc123"],
            "metadatas": [
                {
                    "prev_paragraf_id": "",
                    "next_paragraf_id": "sfs_1974_152_1kap_2§_def456",
                    "kapitel": "1 kap.",
                    "kapitel_rubrik": "Statsskickets grunder",
                }
            ],
            "documents": ["RF 1 kap. 1 §\nAll offentlig makt..."],
        },
        # Second call: fetch sibling chunks
        {
            "ids": ["sfs_1974_152_1kap_2§_def456"],
            "metadatas": [{}],
            "documents": ["RF 1 kap. 2 §\nDen offentliga makten ska utövas..."],
        },
    ]

    orchestrator = MagicMock(spec=RetrievalOrchestrator)
    orchestrator.client = MagicMock()

    result = _make_search_result()

    with patch(
        "app.services.retrieval_orchestrator._get_collection_with_fallback",
        return_value=("sfs_lagtext_jina_v3_1024", mock_collection),
    ):
        expanded = await RetrievalOrchestrator._expand_sfs_context(orchestrator, [result])

    assert len(expanded) == 1
    # Should contain chapter rubrik and next sibling
    assert "Statsskickets grunder" in expanded[0].snippet
    assert "Efterföljande" in expanded[0].snippet


@pytest.mark.asyncio
async def test_expand_sfs_context_missing_sibling_graceful():
    """Missing sibling should not crash, just skip expansion."""
    mock_collection = MagicMock()

    mock_collection.get.side_effect = [
        # Metadata fetch: has sibling ID but sibling doesn't exist
        {
            "ids": ["sfs_1974_152_1kap_1§_abc123"],
            "metadatas": [
                {
                    "prev_paragraf_id": "nonexistent_id",
                    "next_paragraf_id": "",
                }
            ],
            "documents": ["RF 1 kap. 1 §\nAll offentlig makt..."],
        },
        # Sibling fetch returns empty (ID not found)
        {
            "ids": [],
            "metadatas": [],
            "documents": [],
        },
    ]

    orchestrator = MagicMock(spec=RetrievalOrchestrator)
    orchestrator.client = MagicMock()

    result = _make_search_result()
    original_snippet = result.snippet

    with patch(
        "app.services.retrieval_orchestrator._get_collection_with_fallback",
        return_value=("sfs_lagtext_jina_v3_1024", mock_collection),
    ):
        expanded = await RetrievalOrchestrator._expand_sfs_context(orchestrator, [result])

    assert len(expanded) == 1
    # Should still have the original snippet (no crash)
    assert expanded[0].snippet == original_snippet


@pytest.mark.asyncio
async def test_expand_sfs_context_empty_results():
    """Empty results list should return empty."""
    orchestrator = MagicMock(spec=RetrievalOrchestrator)
    expanded = await RetrievalOrchestrator._expand_sfs_context(orchestrator, [])
    assert expanded == []


# ── _chunk_id_to_parent_id tests ────────────────────────────────────


class TestChunkIdToParentId:
    """Tests for parsing ChromaDB chunk IDs to parent store parent_ids."""

    def test_with_kapitel(self):
        """Standard chunk with kapitel: sfs_1974_152_2kap_3§_hash → 1974:152_2_kap"""
        result = RetrievalOrchestrator._chunk_id_to_parent_id("sfs_1974_152_2kap_3§_5f0cb3fa1234")
        assert result == "1974:152_2_kap"

    def test_with_kapitel_a_suffix(self):
        """Kapitel with letter suffix: sfs_1962_700_4akap_1§_hash → 1962:700_4a_kap"""
        result = RetrievalOrchestrator._chunk_id_to_parent_id("sfs_1962_700_4akap_1§_abcdef012345")
        assert result == "1962:700_4a_kap"

    def test_without_kapitel(self):
        """Chunk without kapitel: sfs_1915_218_1§_hash → 1915:218_root"""
        result = RetrievalOrchestrator._chunk_id_to_parent_id("sfs_1915_218_1§_a3b2c1d40000")
        assert result == "1915:218_root"

    def test_non_sfs_id(self):
        """Non-SFS chunk IDs should return None."""
        result = RetrievalOrchestrator._chunk_id_to_parent_id("riksdag_doc_12345_chunk_0")
        assert result is None

    def test_empty_string(self):
        """Empty string should return None."""
        result = RetrievalOrchestrator._chunk_id_to_parent_id("")
        assert result is None

    def test_paragraf_a_suffix(self):
        """Paragraf with letter suffix: sfs_1942_740_3kap_2a§_hash → 1942:740_3_kap"""
        result = RetrievalOrchestrator._chunk_id_to_parent_id("sfs_1942_740_3kap_2a§_deadbeef0000")
        assert result == "1942:740_3_kap"
