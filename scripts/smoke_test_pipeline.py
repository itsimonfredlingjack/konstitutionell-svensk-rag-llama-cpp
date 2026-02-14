#!/usr/bin/env python3
"""
Live smoke test for the Constitutional AI query pipeline.

What this script does:
1. Sends 3 fixed legal test questions to the live API endpoint.
2. Runs internal service-level instrumentation for each question.
3. Logs:
   - Expanded queries
   - Dense/BM25 result counts
   - RRF top-5 doc IDs
   - Reranker top-5 scores
   - CRAG grading per document
   - Final LLM answer preview (first 200 chars)
   - Latency breakdown: expansion, retrieval, reranking, grading, generation, total
4. Prints a compact summary table.

Usage:
    python scripts/smoke_test_pipeline.py
    python scripts/smoke_test_pipeline.py --base-url http://localhost:8900
    python scripts/smoke_test_pipeline.py --output-json data/smoke_test_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

# Make backend package importable when run from repository root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

TEST_QUESTIONS = [
    "Vad säger arbetsmiljölagen om arbetsgivarens ansvar?",
    "Vilka regler gäller för uppsägning enligt LAS?",
    "Hur definieras diskriminering i diskrimineringslagen?",
]


@dataclass
class LatencyBreakdown:
    expansion_ms: float
    retrieval_ms: float
    reranking_ms: float
    grading_ms: float
    generation_ms: float
    total_pipeline_ms: float
    live_http_ms: float


@dataclass
class QuestionReport:
    question: str
    expanded_queries: list[str]
    dense_result_count: int
    bm25_result_count: int
    rrf_top5_doc_ids: list[str]
    reranker_top5_scores: list[float]
    crag_grades: list[dict[str, Any]]
    final_answer_preview: str
    endpoint_status_code: int
    endpoint_success: bool
    latencies: LatencyBreakdown


def _format_ms(value: float) -> str:
    return f"{value:.1f}"


def _truncate(text: str, limit: int = 200) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit]


def _print_header(title: str) -> None:
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def _print_table(rows: list[list[str]], headers: list[str]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_line(values: list[str]) -> str:
        return " | ".join(values[i].ljust(widths[i]) for i in range(len(values)))

    print(fmt_line(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt_line(row))


async def _call_live_endpoint(
    client: httpx.AsyncClient,
    endpoint: str,
    question: str,
    mode: str,
    timeout: float,
) -> tuple[bool, int, str, float]:
    payload = {"question": question, "mode": mode, "history": []}
    start = time.perf_counter()
    try:
        response = await client.post(endpoint, json=payload, timeout=timeout)
        elapsed_ms = (time.perf_counter() - start) * 1000
        data = response.json() if response.content else {}
        answer = data.get("answer", "") if isinstance(data, dict) else ""
        return response.is_success, response.status_code, answer, elapsed_ms
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return False, 0, f"Endpoint call failed: {exc}", elapsed_ms


async def _collect_internal_pipeline_data(
    question: str,
    mode: str,
) -> dict[str, Any]:
    from app.services.config_service import get_config_service
    from app.services.grader_service import get_grader_service
    from app.services.orchestrator_service import get_orchestrator_service
    from app.services.query_expansion_service import QueryExpansionService
    from app.services.reranking_service import get_reranking_service

    config = get_config_service()
    orchestrator = get_orchestrator_service(config=config)
    await orchestrator.initialize()

    try:
        # Expansion details (exact generated alternatives).
        expansion_service = QueryExpansionService(
            config=config, llm_service=orchestrator.llm_service
        )
        expansion_result = await expansion_service.expand(question, count=3)

        # Raw retrieval stage (before grading/reranking).
        retrieval_result = await orchestrator.retrieval.search_with_epr(
            query=question,
            k=10,
            where_filter=None,
            history=None,
        )
        rrf_top5_doc_ids = [doc.id for doc in retrieval_result.results[:5]]
        dense_count = retrieval_result.metrics.dense_result_count
        bm25_count = retrieval_result.metrics.bm25_result_count

        # Reranker scores for top docs.
        reranker = get_reranking_service(config)
        await reranker.initialize()
        rerank_result = await reranker.rerank(
            query=question,
            documents=[
                {"id": d.id, "title": d.title, "snippet": d.snippet, "score": d.score}
                for d in retrieval_result.results
            ],
            top_k=min(5, len(retrieval_result.results)),
        )
        reranker_scores = [round(float(score), 4) for score in rerank_result.reranked_scores[:5]]

        # CRAG grading per doc.
        grader = get_grader_service(config)
        await grader.initialize()
        grading_result = await grader.grade_documents(question, retrieval_result.results)
        crag_grades = [
            {
                "doc_id": grade.doc_id,
                "relevant": grade.relevant,
                "score": round(float(grade.score), 4),
                "confidence": round(float(grade.confidence), 4),
                "reason": grade.reason,
            }
            for grade in grading_result.grades[:5]
        ]

        # Full pipeline timing from orchestrator run.
        pipeline_result = await orchestrator.process_query(
            question=question,
            mode=mode,
            k=10,
            history=None,
            use_agent=False,
        )
        metrics = pipeline_result.metrics

        return {
            "expanded_queries": expansion_result.queries,
            "expansion_latency_ms": expansion_result.latency_ms,
            "dense_result_count": dense_count,
            "bm25_result_count": bm25_count,
            "rrf_top5_doc_ids": rrf_top5_doc_ids,
            "reranker_top5_scores": reranker_scores,
            "crag_grades": crag_grades,
            "retrieval_ms": metrics.retrieval_ms,
            "reranking_ms": metrics.reranking_ms,
            "grading_ms": metrics.grade_ms,
            "generation_ms": metrics.llm_generation_ms,
            "total_pipeline_ms": metrics.total_pipeline_ms,
        }
    finally:
        await orchestrator.close()


async def run_smoke_test(
    *,
    base_url: str,
    endpoint: str,
    mode: str,
    timeout: float,
) -> list[QuestionReport]:
    reports: list[QuestionReport] = []
    full_endpoint = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    async with httpx.AsyncClient() as client:
        for idx, question in enumerate(TEST_QUESTIONS, start=1):
            _print_header(f"Question {idx}: {question}")

            endpoint_success, status_code, answer, http_ms = await _call_live_endpoint(
                client=client,
                endpoint=full_endpoint,
                question=question,
                mode=mode,
                timeout=timeout,
            )
            print(
                f"Live endpoint: status={status_code or 'ERR'} "
                f"success={endpoint_success} latency={_format_ms(http_ms)}ms"
            )

            internal = await _collect_internal_pipeline_data(question=question, mode=mode)

            print(f"Expanded queries ({len(internal['expanded_queries'])}):")
            for q in internal["expanded_queries"]:
                print(f"  - {q}")

            print(
                "Retriever counts: "
                f"dense={internal['dense_result_count']} bm25={internal['bm25_result_count']}"
            )
            print(f"RRF top-5 doc IDs: {internal['rrf_top5_doc_ids']}")
            print(f"Reranker top-5 scores: {internal['reranker_top5_scores']}")

            print("CRAG grading (top-5 docs):")
            for grade in internal["crag_grades"]:
                reason = _truncate(grade["reason"], 120)
                print(
                    f"  - {grade['doc_id']}: relevant={grade['relevant']} "
                    f"score={grade['score']} confidence={grade['confidence']} "
                    f"reason='{reason}'"
                )

            answer_preview = _truncate(answer, 200)
            print(f"Final LLM answer (first 200 chars): {answer_preview}")

            latency = LatencyBreakdown(
                expansion_ms=float(internal["expansion_latency_ms"]),
                retrieval_ms=float(internal["retrieval_ms"]),
                reranking_ms=float(internal["reranking_ms"]),
                grading_ms=float(internal["grading_ms"]),
                generation_ms=float(internal["generation_ms"]),
                total_pipeline_ms=float(internal["total_pipeline_ms"]),
                live_http_ms=http_ms,
            )
            print("Latency breakdown (ms):")
            print(
                f"  expansion={latency.expansion_ms:.1f}, "
                f"retrieval={latency.retrieval_ms:.1f}, "
                f"reranking={latency.reranking_ms:.1f}, "
                f"grading={latency.grading_ms:.1f}, "
                f"generation={latency.generation_ms:.1f}, "
                f"total={latency.total_pipeline_ms:.1f}, "
                f"live_http={latency.live_http_ms:.1f}"
            )

            reports.append(
                QuestionReport(
                    question=question,
                    expanded_queries=internal["expanded_queries"],
                    dense_result_count=internal["dense_result_count"],
                    bm25_result_count=internal["bm25_result_count"],
                    rrf_top5_doc_ids=internal["rrf_top5_doc_ids"],
                    reranker_top5_scores=internal["reranker_top5_scores"],
                    crag_grades=internal["crag_grades"],
                    final_answer_preview=answer_preview,
                    endpoint_status_code=status_code,
                    endpoint_success=endpoint_success,
                    latencies=latency,
                )
            )

    return reports


def _print_summary(reports: list[QuestionReport]) -> None:
    _print_header("Smoke test summary")

    rows: list[list[str]] = []
    for report in reports:
        rows.append(
            [
                _truncate(report.question, 44),
                str(len(report.expanded_queries)),
                str(report.dense_result_count),
                str(report.bm25_result_count),
                _format_ms(report.latencies.total_pipeline_ms),
                _format_ms(report.latencies.live_http_ms),
                "OK" if report.endpoint_success else "FAIL",
            ]
        )

    headers = [
        "Question",
        "Expanded",
        "Dense",
        "BM25",
        "Pipeline ms",
        "Live ms",
        "Endpoint",
    ]
    _print_table(rows, headers)

    if reports:
        avg_total = sum(r.latencies.total_pipeline_ms for r in reports) / len(reports)
        avg_live = sum(r.latencies.live_http_ms for r in reports) / len(reports)
        avg_exp = sum(r.latencies.expansion_ms for r in reports) / len(reports)
        print("\nAverages:")
        print(f"  expansion={avg_exp:.1f}ms pipeline={avg_total:.1f}ms live_http={avg_live:.1f}ms")


def _evaluate_gates(
    reports: list[QuestionReport],
    *,
    min_endpoint_success_rate: float,
    min_dense_hits_avg: float,
    min_bm25_hits_avg: float,
    max_pipeline_ms_avg: float,
) -> tuple[bool, list[list[str]]]:
    if not reports:
        return False, [["reports_present", "0", ">= 1", "FAIL"]]

    total = float(len(reports))
    success_rate = sum(1 for r in reports if r.endpoint_success) / total
    dense_avg = sum(r.dense_result_count for r in reports) / total
    bm25_avg = sum(r.bm25_result_count for r in reports) / total
    pipeline_avg = sum(r.latencies.total_pipeline_ms for r in reports) / total

    checks = [
        (
            "endpoint_success_rate",
            success_rate,
            f">= {min_endpoint_success_rate:.4f}",
            success_rate >= min_endpoint_success_rate,
        ),
        (
            "dense_hits_avg",
            dense_avg,
            f">= {min_dense_hits_avg:.4f}",
            dense_avg >= min_dense_hits_avg,
        ),
        ("bm25_hits_avg", bm25_avg, f">= {min_bm25_hits_avg:.4f}", bm25_avg >= min_bm25_hits_avg),
        (
            "pipeline_ms_avg",
            pipeline_avg,
            f"<= {max_pipeline_ms_avg:.4f}",
            pipeline_avg <= max_pipeline_ms_avg,
        ),
    ]
    rows = [
        [name, f"{value:.4f}", threshold, "PASS" if ok else "FAIL"]
        for name, value, threshold, ok in checks
    ]
    return all(ok for _, _, _, ok in checks), rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live smoke test for the legal RAG pipeline.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8900",
        help="Base URL for API server (default: http://localhost:8900).",
    )
    parser.add_argument(
        "--endpoint",
        default="/api/constitutional/agent/query",
        help="Query endpoint path (default: /api/constitutional/agent/query).",
    )
    parser.add_argument(
        "--mode",
        default="evidence",
        choices=["auto", "chat", "assist", "evidence"],
        help="Query mode sent to endpoint/internal pipeline.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds for endpoint call.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write full JSON report.",
    )
    parser.add_argument("--enforce-gates", action="store_true")
    parser.add_argument("--min-endpoint-success-rate", type=float, default=1.0)
    parser.add_argument("--min-dense-hits-avg", type=float, default=1.0)
    parser.add_argument("--min-bm25-hits-avg", type=float, default=1.0)
    parser.add_argument("--max-pipeline-ms-avg", type=float, default=20000.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reports = asyncio.run(
        run_smoke_test(
            base_url=args.base_url,
            endpoint=args.endpoint,
            mode=args.mode,
            timeout=args.timeout,
        )
    )
    _print_summary(reports)

    gates_ok, gate_rows = _evaluate_gates(
        reports,
        min_endpoint_success_rate=args.min_endpoint_success_rate,
        min_dense_hits_avg=args.min_dense_hits_avg,
        min_bm25_hits_avg=args.min_bm25_hits_avg,
        max_pipeline_ms_avg=args.max_pipeline_ms_avg,
    )
    print("\nSmoke DoD gates:")
    _print_table(gate_rows, ["Metric", "Value", "Threshold", "Result"])
    print(f"\nSmoke overall: {'PASS' if gates_ok else 'FAIL'}")

    if args.enforce_gates and not gates_ok:
        raise SystemExit(2)

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(report) for report in reports]
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDetailed report written to: {output_path}")


if __name__ == "__main__":
    main()
