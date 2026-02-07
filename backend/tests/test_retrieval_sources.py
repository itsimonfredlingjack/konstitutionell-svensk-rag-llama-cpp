"""
Retrieval Source Integration Tests

P0: The RAG pipeline must return sources for known-good queries.
If sources are empty, the system is hallucinating — unacceptable for
a constitutional verification tool.

These tests exist because commit d34cf1f introduced a MIN_SCORE filter
that silently killed ALL sources when RAG-Fusion (RRF) was active,
since RRF scores (~0.04 max) are on a completely different scale than
the ChromaDB similarity scores (0-1) the filter was written for.

INVARIANTS:
1. Known legal queries MUST return at least 1 source
2. evidence_level must NOT be "none" when sources exist
3. saknas_underlag must be True when sources are empty
4. Source scores must be > 0 (not placeholder zeros)
5. Every source must have required fields (id, title, snippet, score)
"""

import pytest
import httpx


BASE_URL = "http://localhost:8900"
TIMEOUT = 120.0

# Queries that MUST return sources — these are core Swedish constitutional law
MUST_HAVE_SOURCES = [
    ("Vad säger yttrandefrihetsgrundlagen?", "sfs"),
    ("Vad säger Regeringsformen om yttrandefrihet?", "sfs"),
    ("Vad säger förvaltningslagen om överklagande?", "sfs"),
]

# Required fields on every source object
REQUIRED_SOURCE_FIELDS = {"id", "title", "snippet", "score", "source"}


# =============================================================================
# Invariant 1: Known queries MUST return sources (never empty)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("query,expected_collection_prefix", MUST_HAVE_SOURCES)
async def test_known_queries_return_sources(query: str, expected_collection_prefix: str):
    """
    P0: Queries about well-known Swedish laws must return at least 1 source.

    If this fails, retrieval is broken — the system will hallucinate answers
    about constitutional law without any grounding.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200, f"API error for: {query}"

        data = response.json()
        sources = data.get("sources", [])

        assert len(sources) > 0, (
            f"CRITICAL: Zero sources for '{query}'. "
            f"The system generated an answer without any grounding. "
            f"Check MIN_SCORE filter vs RRF score scale in retrieval_orchestrator.py"
        )

        # At least one source should be from the expected collection
        matching = [s for s in sources if expected_collection_prefix in s.get("source", "").lower()]
        assert len(matching) > 0, (
            f"No sources from '{expected_collection_prefix}' collection for '{query}'. "
            f"Got: {[s.get('source') for s in sources]}"
        )


# =============================================================================
# Invariant 2: Source objects must have required fields
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_source_objects_have_required_fields():
    """
    Every source object must contain id, title, snippet, score, and source.
    Missing fields break the frontend and make sources unusable.
    """
    query = "Vad säger Regeringsformen om yttrandefrihet?"

    async with httpx.AsyncClient(timeout=TIMEOUT, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])
        assert len(sources) > 0, "Need sources to validate fields"

        for i, source in enumerate(sources):
            missing = REQUIRED_SOURCE_FIELDS - set(source.keys())
            assert (
                not missing
            ), f"Source [{i}] missing fields: {missing}. Got keys: {list(source.keys())}"
            assert (
                source["score"] > 0
            ), f"Source [{i}] has score=0 — likely a placeholder. Title: {source.get('title')}"


# =============================================================================
# Invariant 3: evidence_level must be consistent with sources
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_evidence_level_not_none_when_sources_exist():
    """
    If the pipeline found sources, evidence_level must not be 'none'.
    A response with sources but evidence_level='none' is self-contradictory.
    """
    query = "Vad säger yttrandefrihetsgrundlagen?"

    async with httpx.AsyncClient(timeout=TIMEOUT, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])
        evidence_level = data.get("evidence_level", "none").lower()

        if len(sources) > 0:
            assert evidence_level != "none", (
                f"Got {len(sources)} sources but evidence_level='none'. "
                f"The system found evidence but claims it didn't."
            )


# =============================================================================
# Invariant 4: saknas_underlag consistency
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_saknas_underlag_true_when_no_sources():
    """
    If sources list is empty, saknas_underlag should be True.
    The system must not claim it has supporting evidence when it doesn't.

    Note: This test uses a nonsense query to trigger zero results.
    """
    query = "xyzzy plugh fee fie foe fum nonsense gibberish 12345"

    async with httpx.AsyncClient(timeout=TIMEOUT, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])

        if len(sources) == 0:
            saknas = data.get("saknas_underlag", None)
            assert saknas is True, (
                f"Zero sources but saknas_underlag={saknas}. "
                f"The system should acknowledge that evidence is missing."
            )


# =============================================================================
# Invariant 5: EVIDENCE mode must use refusal text when no sources
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_evidence_mode_refuses_when_no_sources():
    """
    In EVIDENCE mode, if no sources are found, the system must return
    the refusal template — never generate a hallucinated answer.

    This is the core guardrail for a constitutional verification tool.
    """
    query = "xyzzy plugh fee fie foe fum nonsense gibberish 12345"

    async with httpx.AsyncClient(timeout=TIMEOUT, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])
        answer = data.get("answer", "")

        if len(sources) == 0:
            # Check for refusal keywords
            refusal_keywords = ["kan inte besvara", "underlag saknas", "spekulera"]
            has_refusal = any(kw.lower() in answer.lower() for kw in refusal_keywords)
            assert has_refusal, (
                f"GUARDRAIL FAILURE: Zero sources in EVIDENCE mode but answer doesn't "
                f"contain refusal language. Answer: {answer[:200]}..."
            )


# =============================================================================
# Invariant 6: Scores are on a sane scale
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_source_scores_are_on_similarity_scale():
    """
    Source scores exposed to the frontend should be on the 0-1 similarity scale,
    not raw RRF scores (which max out at ~0.04 for k=45).

    This catches the exact bug from the MIN_SCORE incident: if scores are all
    below 0.1, they're likely RRF scores leaking through instead of similarity.
    """
    query = "Vad säger Regeringsformen om yttrandefrihet?"

    async with httpx.AsyncClient(timeout=TIMEOUT, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])
        assert len(sources) > 0, "Need sources to check score scale"

        max_score = max(s["score"] for s in sources)
        assert max_score > 0.1, (
            f"Highest source score is {max_score:.4f} — suspiciously low. "
            f"Scores should be ChromaDB similarity (0-1 range), not RRF (~0.01-0.04). "
            f"Check if rrf_score is leaking into the response instead of original_score."
        )
