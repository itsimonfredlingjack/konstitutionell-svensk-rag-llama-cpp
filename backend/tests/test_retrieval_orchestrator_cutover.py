import pytest

from app.services.retrieval_orchestrator import RetrievalMetrics, RetrievalOrchestrator


class _MockClient:
    def __init__(self, collection_names):
        self._collections = {name: object() for name in collection_names}

    def get_collection(self, name):
        if name in self._collections:
            return self._collections[name]
        raise ValueError(f"Collection {name} not found")


def _embed(queries):
    return [[0.0] for _ in queries]


def test_cutover_disabled_allows_fallback_resolution():
    orchestrator = RetrievalOrchestrator(
        chromadb_client=_MockClient(["sfs_lagtext_bge_m3_1024"]),
        embedding_function=_embed,
        default_collections=["sfs_lagtext_jina_v3_1024"],
        cutover_enforce_jina_collections=False,
    )
    metrics = RetrievalMetrics()

    orchestrator._enforce_cutover_policy(["sfs_lagtext_jina_v3_1024"], metrics)

    assert metrics.cutover_enforced is False
    assert metrics.cutover_violation is True
    assert "sfs_lagtext_jina_v3_1024" in metrics.cutover_violation_collections


def test_cutover_enabled_raises_on_fallback_resolution():
    orchestrator = RetrievalOrchestrator(
        chromadb_client=_MockClient(["sfs_lagtext_bge_m3_1024"]),
        embedding_function=_embed,
        default_collections=["sfs_lagtext_jina_v3_1024"],
        cutover_enforce_jina_collections=True,
    )
    metrics = RetrievalMetrics()

    with pytest.raises(RuntimeError) as exc_info:
        orchestrator._enforce_cutover_policy(["sfs_lagtext_jina_v3_1024"], metrics)
    assert "CUTOVER_VIOLATION" in str(exc_info.value)

    assert metrics.cutover_enforced is True
    assert metrics.cutover_violation is True
    assert metrics.cutover_violation_collections == ["sfs_lagtext_jina_v3_1024"]


def test_cutover_allowlist_permits_specific_fallback():
    orchestrator = RetrievalOrchestrator(
        chromadb_client=_MockClient(["sfs_lagtext_bge_m3_1024"]),
        embedding_function=_embed,
        default_collections=["sfs_lagtext_jina_v3_1024"],
        cutover_enforce_jina_collections=True,
        cutover_allowed_fallback_collections=["sfs_lagtext_jina_v3_1024"],
    )
    metrics = RetrievalMetrics()

    orchestrator._enforce_cutover_policy(["sfs_lagtext_jina_v3_1024"], metrics)

    assert metrics.cutover_enforced is True
    assert metrics.cutover_violation is False
    assert metrics.cutover_violation_collections == []


@pytest.mark.asyncio
async def test_parallel_search_returns_cutover_violation_error_when_enforced():
    orchestrator = RetrievalOrchestrator(
        chromadb_client=_MockClient(["sfs_lagtext_bge_m3_1024"]),
        embedding_function=_embed,
        default_collections=["sfs_lagtext_jina_v3_1024"],
        cutover_enforce_jina_collections=True,
    )

    result = await orchestrator.search(
        query="Vad säger arbetsmiljölagen?",
        collections=["sfs_lagtext_jina_v3_1024"],
    )

    assert result.success is False
    assert result.error is not None
    assert "CUTOVER_VIOLATION" in result.error
