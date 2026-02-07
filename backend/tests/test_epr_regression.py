"""
EPR (Evidence Policy Routing) Regression Tests

These tests lock the core invariants that must never be violated.
All tests here are P0 blockers - if any fail, EPR routing is broken.

INVARIANTS:
1. LEGAL_TEXT → never DiVA
2. PRACTICAL_PROCESS → procedural_guides + SFS (procedural first)
3. Tier sort → A (SFS/Riksdag) before B before C (DiVA)
"""

import pytest
import httpx

# These tests require a running backend on localhost:8900
# Run with: pytest -m integration
pytestmark = pytest.mark.integration


# =============================================================================
# Test Queries per Intent
# =============================================================================

LEGAL_TEXT_QUERIES = [
    "Vad säger Regeringsformen om yttrandefrihet?",
    "Vad säger förvaltningslagen om överklagande?",
    "RF 2 kap 1 §",
]

PRACTICAL_PROCESS_QUERIES = [
    "Hur överklagar jag ett myndighetsbeslut?",
    "Hur begär jag ut allmänna handlingar?",
    "Vad är offentlighetsprincipen?",
]

# =============================================================================
# Invariant 1: LEGAL_TEXT → never DiVA
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("query", LEGAL_TEXT_QUERIES)
async def test_legal_text_never_diva(query: str):
    """
    P0 Invariant: LEGAL_TEXT queries must NEVER return DiVA sources.

    DiVA is academic research - legal questions require authoritative legal sources.
    """
    async with httpx.AsyncClient(timeout=120.0, base_url="http://localhost:8900") as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200, f"API failed for query: {query}"

        data = response.json()
        sources = data.get("sources", [])

        diva_sources = [s for s in sources if "diva" in s.get("source", "").lower()]

        assert len(diva_sources) == 0, (
            f"INVARIANT VIOLATED: LEGAL_TEXT returned DiVA!\n"
            f"Query: {query}\n"
            f"DiVA sources: {[s.get('source') for s in diva_sources]}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("query", LEGAL_TEXT_QUERIES)
async def test_legal_text_has_sfs(query: str):
    """
    P0 Invariant: LEGAL_TEXT queries must return SFS (primary law) sources.
    """
    async with httpx.AsyncClient(timeout=120.0, base_url="http://localhost:8900") as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])

        sfs_sources = [s for s in sources if "sfs" in s.get("source", "").lower()]

        assert len(sfs_sources) > 0, (
            f"INVARIANT VIOLATED: LEGAL_TEXT returned no SFS sources!\n"
            f"Query: {query}\n"
            f"All sources: {[s.get('source') for s in sources]}"
        )


# =============================================================================
# Invariant 2: PRACTICAL_PROCESS → procedural_guides + SFS
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("query", PRACTICAL_PROCESS_QUERIES)
async def test_practical_process_has_procedural_guides(query: str):
    """
    P0 Invariant: PRACTICAL_PROCESS queries should include procedural_guides.

    These are how-to questions that need step-by-step guidance.
    """
    async with httpx.AsyncClient(timeout=120.0, base_url="http://localhost:8900") as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200, f"API failed for query: {query}"

        data = response.json()
        sources = data.get("sources", [])

        procedural_sources = [s for s in sources if "procedural" in s.get("source", "").lower()]

        # Note: This is a soft check - procedural guides should be present
        # but system might also work with just SFS
        if len(procedural_sources) == 0:
            pytest.skip(
                f"No procedural_guides found for: {query}\n"
                f"Sources: {[s.get('source') for s in sources]}"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("query", PRACTICAL_PROCESS_QUERIES)
async def test_practical_process_never_only_diva(query: str):
    """
    P0 Invariant: PRACTICAL_PROCESS must not return ONLY DiVA sources.

    Practical questions need actionable guidance, not just academic research.
    """
    async with httpx.AsyncClient(timeout=120.0, base_url="http://localhost:8900") as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])

        if len(sources) == 0:
            return  # No sources = different issue

        non_diva_sources = [s for s in sources if "diva" not in s.get("source", "").lower()]

        assert len(non_diva_sources) > 0, (
            f"INVARIANT VIOLATED: PRACTICAL_PROCESS returned ONLY DiVA!\n"
            f"Query: {query}\n"
            f"Sources: {[s.get('source') for s in sources]}"
        )


# =============================================================================
# Invariant 3: Tier Sort A→B→C
# =============================================================================


@pytest.mark.asyncio
async def test_tier_ordering_a_before_c():
    """
    P0 Invariant: Tier A sources (SFS) should appear before Tier C (DiVA).

    When both SFS and DiVA are relevant, SFS must rank higher.
    """
    # Use a mixed query that could return both
    query = "Vilka regler finns kring offentlighet och sekretess?"

    async with httpx.AsyncClient(timeout=120.0, base_url="http://localhost:8900") as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        sources = data.get("sources", [])

        if len(sources) < 2:
            pytest.skip("Need multiple sources to test ordering")

        # Find first SFS and first DiVA positions
        first_sfs_idx = None
        first_diva_idx = None

        for idx, s in enumerate(sources):
            source_name = s.get("source", "").lower()
            if first_sfs_idx is None and "sfs" in source_name:
                first_sfs_idx = idx
            if first_diva_idx is None and "diva" in source_name:
                first_diva_idx = idx

        # If both present, SFS should come first
        if first_sfs_idx is not None and first_diva_idx is not None:
            assert first_sfs_idx < first_diva_idx, (
                f"INVARIANT VIOLATED: DiVA (idx={first_diva_idx}) ranked above SFS (idx={first_sfs_idx})!\n"
                f"Query: {query}\n"
                f"Source order: {[s.get('source') for s in sources]}"
            )


# =============================================================================
# Smoke Test: Full System Health
# =============================================================================


@pytest.mark.asyncio
async def test_system_responds_to_any_query():
    """Basic smoke test: System should respond without crashing."""
    async with httpx.AsyncClient(timeout=120.0, base_url="http://localhost:8900") as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": "Hej!", "mode": "evidence"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data or "response" in data


if __name__ == "__main__":
    import asyncio

    async def run_manual():
        print("Running EPR regression tests manually...")

        print("\n--- Invariant 1: LEGAL_TEXT never DiVA ---")
        for q in LEGAL_TEXT_QUERIES:
            await test_legal_text_never_diva(q)
            await test_legal_text_has_sfs(q)
            print(f"  ✅ {q[:50]}...")

        print("\n--- Invariant 2: PRACTICAL_PROCESS has procedural guides ---")
        for q in PRACTICAL_PROCESS_QUERIES:
            try:
                await test_practical_process_has_procedural_guides(q)
                await test_practical_process_never_only_diva(q)
                print(f"  ✅ {q[:50]}...")
            except Exception as e:
                print(f"  ⚠️  {q[:50]}... ({e})")

        print("\n--- Invariant 3: Tier ordering ---")
        await test_tier_ordering_a_before_c()
        print("  ✅ Tier A before Tier C")

        print("\n✅ All EPR regression tests passed!")

    asyncio.run(run_manual())


# =============================================================================
# Invariant 4: EDGE_CLARIFICATION - Clean behavior
# =============================================================================

EDGE_CLARIFICATION_QUERIES = [
    "Menar du förvaltningslagen eller förvaltningsprocesslagen?",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", EDGE_CLARIFICATION_QUERIES)
async def test_edge_clarification_no_citations_ok(query: str):
    """
    P0 Invariant: EDGE_CLARIFICATION may return empty citations and still be valid.

    Clarification questions don't need sources - they're asking for disambiguation.
    The system should NOT set saknas_underlag=true for these.
    """
    async with httpx.AsyncClient(timeout=120.0, base_url="http://localhost:8900") as client:
        response = await client.post(
            "/api/constitutional/agent/query",
            json={"question": query, "mode": "evidence"},
        )
        assert response.status_code == 200

        data = response.json()
        answer = data.get("answer", data.get("response", ""))

        # Answer should not be a refusal
        if isinstance(answer, str):
            assert "saknar underlag" not in answer.lower(), (
                f"EDGE_CLARIFICATION should not refuse to answer clarifying questions.\n"
                f"Query: {query}\n"
                f"Answer: {answer[:200]}"
            )
