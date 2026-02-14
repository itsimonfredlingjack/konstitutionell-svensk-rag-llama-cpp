from dataclasses import dataclass

from app.services.retrieval_orchestrator import RetrievalOrchestrator


@dataclass
class _RewriteResult:
    lexical_query: str


def _embed(queries):
    return [[0.0] for _ in queries]


def test_build_bm25_query_uses_lexical_query_and_llm_expansions():
    orchestrator = RetrievalOrchestrator(
        chromadb_client=object(),
        embedding_function=_embed,
        default_collections=["sfs_lagtext_jina_v3_1024"],
    )
    rewrite_result = _RewriteResult(lexical_query="gdpr samtycke")

    bm25_query = orchestrator._build_bm25_query(
        base_query="Vad säger GDPR om samtycke?",
        rewrite_result=rewrite_result,
        llm_expansions=["personuppgifter behandling", "dataskyddsforordningen samtycke"],
    )

    assert "gdpr samtycke" in bm25_query
    assert "personuppgifter behandling" in bm25_query
    assert "dataskyddsforordningen samtycke" in bm25_query


def test_build_bm25_query_deduplicates_terms_case_insensitive():
    orchestrator = RetrievalOrchestrator(
        chromadb_client=object(),
        embedding_function=_embed,
        default_collections=["sfs_lagtext_jina_v3_1024"],
    )

    bm25_query = orchestrator._build_bm25_query(
        base_query="GDPR samtycke",
        rewrite_result=None,
        llm_expansions=["gdpr samtycke", "GDPR SAMTYCKE", "personuppgifter"],
    )

    assert bm25_query.count("GDPR samtycke") == 1
    assert "personuppgifter" in bm25_query
