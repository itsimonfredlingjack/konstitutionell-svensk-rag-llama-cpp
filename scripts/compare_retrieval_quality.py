#!/usr/bin/env python3
"""
Compare retrieval quality and latency across 10 legal test questions.

Outputs:
- Human-readable summary table in terminal
- Full JSON report at logs/retrieval_quality_benchmark.json by default
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

BENCHMARK_QUESTIONS = [
    "Vad säger arbetsmiljölagen om arbetsgivarens ansvar?",
    "Vilka regler gäller för uppsägning enligt LAS?",
    "Hur definieras diskriminering i diskrimineringslagen?",
    "Vad innebär arbetsgivarens rehabiliteringsansvar?",
    "Vilka tidsfrister gäller vid uppsägning på grund av arbetsbrist?",
    "Hur regleras övertidsarbete i arbetstidslagen?",
    "Vad säger semesterlagen om semesterlönegrundande frånvaro?",
    "Vilka krav ställer GDPR på personuppgiftsansvariga?",
    "Hur definieras systematiskt arbetsmiljöarbete enligt AFS 2001:1?",
    "Vad gäller för provanställning enligt LAS?",
]

DEFAULT_GATES = {
    "max_pipeline_ms_avg": 15000.0,
    "max_pipeline_ms_p95": 25000.0,
    "min_live_success_rate": 0.95,
    "min_dense_hits_avg": 1.0,
    "min_bm25_hits_avg": 1.0,
    "min_crag_yes_rate_top5": 0.20,
}


def _truncate(text: str, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


def _print_table(rows: list[list[str]], headers: list[str]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(values: list[str]) -> str:
        return " | ".join(values[i].ljust(widths[i]) for i in range(len(values)))

    print(fmt(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt(row))


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = math.ceil(0.95 * len(sorted_values)) - 1
    idx = max(0, min(idx, len(sorted_values) - 1))
    return float(sorted_values[idx])


def _build_summary(results: list[dict[str, Any]]) -> dict[str, float]:
    if not results:
        return {
            "expanded": 0.0,
            "dense": 0.0,
            "bm25": 0.0,
            "expansion_ms": 0.0,
            "dense_ms": 0.0,
            "bm25_ms": 0.0,
            "rrf_ms": 0.0,
            "rerank_ms": 0.0,
            "grading_ms": 0.0,
            "generation_ms": 0.0,
            "pipeline_ms_avg": 0.0,
            "pipeline_ms_p95": 0.0,
            "live_ms_avg": 0.0,
            "live_success_rate": 0.0,
            "crag_yes_rate_top5": 0.0,
        }

    n = float(len(results))
    pipeline_values = [float(item["latency_ms"]["pipeline_total"]) for item in results]
    live_successes = sum(1 for item in results if item["live"]["success"])

    crag_yes = 0
    crag_total = 0
    for item in results:
        for grade in item.get("crag_grading", [])[:5]:
            crag_total += 1
            if str(grade.get("relevance", "")).lower() == "yes":
                crag_yes += 1

    return {
        "expanded": sum(len(item["expanded_queries"]) for item in results) / n,
        "dense": sum(item["dense_count"] for item in results) / n,
        "bm25": sum(item["bm25_count"] for item in results) / n,
        "expansion_ms": sum(item["latency_ms"]["expansion"] for item in results) / n,
        "dense_ms": sum(item["latency_ms"]["dense"] for item in results) / n,
        "bm25_ms": sum(item["latency_ms"]["bm25"] for item in results) / n,
        "rrf_ms": sum(item["latency_ms"]["rrf"] for item in results) / n,
        "rerank_ms": sum(item["latency_ms"]["rerank"] for item in results) / n,
        "grading_ms": sum(item["latency_ms"]["grading"] for item in results) / n,
        "generation_ms": sum(item["latency_ms"]["generation"] for item in results) / n,
        "pipeline_ms_avg": sum(pipeline_values) / n,
        "pipeline_ms_p95": _p95(pipeline_values),
        "live_ms_avg": sum(item["live"]["latency_ms"] for item in results) / n,
        "live_success_rate": float(live_successes) / n,
        "crag_yes_rate_top5": (float(crag_yes) / float(crag_total)) if crag_total else 0.0,
    }


def _load_gate_overrides(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    gate_path = Path(path)
    if not gate_path.exists():
        raise FileNotFoundError(f"Gate config file not found: {gate_path}")
    payload = json.loads(gate_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gate config must be a JSON object.")
    return {str(k): float(v) for k, v in payload.items()}


def _evaluate_gates(
    summary: dict[str, float], gates: dict[str, float]
) -> tuple[bool, list[list[str]]]:
    checks = [
        (
            "live_success_rate",
            summary["live_success_rate"],
            ">=",
            gates["min_live_success_rate"],
            summary["live_success_rate"] >= gates["min_live_success_rate"],
        ),
        (
            "pipeline_ms_avg",
            summary["pipeline_ms_avg"],
            "<=",
            gates["max_pipeline_ms_avg"],
            summary["pipeline_ms_avg"] <= gates["max_pipeline_ms_avg"],
        ),
        (
            "pipeline_ms_p95",
            summary["pipeline_ms_p95"],
            "<=",
            gates["max_pipeline_ms_p95"],
            summary["pipeline_ms_p95"] <= gates["max_pipeline_ms_p95"],
        ),
        (
            "dense_hits_avg",
            summary["dense"],
            ">=",
            gates["min_dense_hits_avg"],
            summary["dense"] >= gates["min_dense_hits_avg"],
        ),
        (
            "bm25_hits_avg",
            summary["bm25"],
            ">=",
            gates["min_bm25_hits_avg"],
            summary["bm25"] >= gates["min_bm25_hits_avg"],
        ),
        (
            "crag_yes_rate_top5",
            summary["crag_yes_rate_top5"],
            ">=",
            gates["min_crag_yes_rate_top5"],
            summary["crag_yes_rate_top5"] >= gates["min_crag_yes_rate_top5"],
        ),
    ]
    rows = [
        [name, f"{value:.4f}", f"{op} {threshold:.4f}", "PASS" if ok else "FAIL"]
        for name, value, op, threshold, ok in checks
    ]
    return all(item[-1] for item in checks), rows


async def _call_live_endpoint(
    client: httpx.AsyncClient,
    endpoint: str,
    question: str,
    mode: str,
    timeout: float,
) -> dict[str, Any]:
    payload = {"question": question, "mode": mode, "history": []}
    start = time.perf_counter()
    try:
        response = await client.post(endpoint, json=payload, timeout=timeout)
        elapsed_ms = (time.perf_counter() - start) * 1000
        data = response.json() if response.content else {}
        answer = data.get("answer", "") if isinstance(data, dict) else ""
        return {
            "success": response.is_success,
            "status_code": response.status_code,
            "answer_preview": _truncate(answer, 300),
            "latency_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "success": False,
            "status_code": 0,
            "answer_preview": f"Endpoint call failed: {exc}",
            "latency_ms": elapsed_ms,
        }


async def _collect_internal(
    orchestrator,
    reranker,
    grader,
    expansion_service,
    question: str,
    mode: str,
) -> dict[str, Any]:
    expansion_result = await expansion_service.expand(question, count=3)
    retrieval_result = await orchestrator.retrieval.search_with_epr(
        query=question,
        k=30,
        where_filter=None,
        history=None,
    )
    retrieval_metrics = retrieval_result.metrics

    rrf_top5 = retrieval_result.results[:5]
    rrf_top5_docs = [
        {
            "id": doc.id,
            "title": doc.title,
            "source": doc.source,
            "score": round(float(doc.score), 4),
            "doc_type": doc.doc_type,
            "date": doc.date,
        }
        for doc in rrf_top5
    ]

    rerank_input = [
        {
            "id": doc.id,
            "title": doc.title,
            "snippet": doc.snippet,
            "score": doc.score,
            "source": doc.source,
            "doc_type": doc.doc_type,
            "date": doc.date,
        }
        for doc in retrieval_result.results
    ]
    rerank_result = await reranker.rerank(query=question, documents=rerank_input, top_k=5)
    reranked_docs = rerank_result.reranked_docs[:5]
    reranked_scores = rerank_result.reranked_scores[:5]

    id_to_doc = {doc.id: doc for doc in retrieval_result.results}
    reranked_search_docs = [id_to_doc[d["id"]] for d in reranked_docs if d["id"] in id_to_doc]
    grading_result = await grader.grade_documents(question, reranked_search_docs)
    grade_by_id = {grade.doc_id: grade for grade in grading_result.grades}

    grading_output = []
    for doc in reranked_docs:
        grade = grade_by_id.get(doc["id"])
        relevance = "yes" if grade and grade.relevant else "no"
        grading_output.append(
            {
                "doc_id": doc["id"],
                "relevance": relevance,
                "score": round(float(grade.score), 4) if grade else 0.0,
                "confidence": round(float(grade.confidence), 4) if grade else 0.0,
                "reason": grade.reason if grade else "missing grade",
            }
        )

    pipeline_result = await orchestrator.process_query(
        question=question,
        mode=mode,
        k=10,
        history=None,
        use_agent=False,
    )

    return {
        "expanded_queries": expansion_result.queries,
        "dense_count": retrieval_metrics.dense_result_count,
        "bm25_count": retrieval_metrics.bm25_result_count,
        "rrf_top5_docs": rrf_top5_docs,
        "reranked_top5_docs": [
            {
                "id": doc["id"],
                "title": doc.get("title", ""),
                "source": doc.get("source", ""),
                "doc_type": doc.get("doc_type"),
                "date": doc.get("date"),
                "reranker_score": round(float(score), 4),
            }
            for doc, score in zip(reranked_docs, reranked_scores)
        ],
        "crag_grading": grading_output,
        "latency_ms": {
            "expansion": round(float(retrieval_metrics.llm_query_expansion_latency_ms), 2),
            "dense": round(float(retrieval_metrics.dense_latency_ms), 2),
            "bm25": round(float(retrieval_metrics.bm25_latency_ms), 2),
            "rrf": round(float(retrieval_metrics.rrf_latency_ms), 2),
            "rerank": round(float(rerank_result.latency_ms), 2),
            "grading": round(float(grading_result.metrics.total_latency_ms), 2),
            "generation": round(float(pipeline_result.metrics.llm_generation_ms), 2),
            "pipeline_total": round(float(pipeline_result.metrics.total_pipeline_ms), 2),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark retrieval quality on 10 legal queries.")
    parser.add_argument("--base-url", default="http://localhost:8900")
    parser.add_argument("--endpoint", default="/api/constitutional/agent/query")
    parser.add_argument(
        "--mode", default="evidence", choices=["auto", "chat", "assist", "evidence"]
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--enforce-gates",
        action="store_true",
        help="Fail with exit code 2 if DoD gates do not pass.",
    )
    parser.add_argument(
        "--gates-config",
        default=None,
        help="Optional JSON file with DoD gate overrides.",
    )
    parser.add_argument("--max-pipeline-ms-avg", type=float, default=None)
    parser.add_argument("--max-pipeline-ms-p95", type=float, default=None)
    parser.add_argument("--min-live-success-rate", type=float, default=None)
    parser.add_argument("--min-dense-hits-avg", type=float, default=None)
    parser.add_argument("--min-bm25-hits-avg", type=float, default=None)
    parser.add_argument("--min-crag-yes-rate-top5", type=float, default=None)
    parser.add_argument(
        "--output-json",
        default="logs/retrieval_quality_benchmark.json",
        help="Path to JSON output (default: logs/retrieval_quality_benchmark.json).",
    )
    return parser.parse_args()


async def main() -> None:
    from app.services.config_service import get_config_service
    from app.services.grader_service import get_grader_service
    from app.services.orchestrator_service import get_orchestrator_service
    from app.services.query_expansion_service import QueryExpansionService
    from app.services.reranking_service import get_reranking_service

    args = _parse_args()
    full_endpoint = f"{args.base_url.rstrip('/')}/{args.endpoint.lstrip('/')}"

    config = get_config_service()
    gates = {
        "max_pipeline_ms_avg": float(
            getattr(
                config.settings,
                "benchmark_max_pipeline_ms_avg",
                DEFAULT_GATES["max_pipeline_ms_avg"],
            )
        ),
        "max_pipeline_ms_p95": float(
            getattr(
                config.settings,
                "benchmark_max_pipeline_ms_p95",
                DEFAULT_GATES["max_pipeline_ms_p95"],
            )
        ),
        "min_live_success_rate": float(
            getattr(
                config.settings,
                "benchmark_min_live_success_rate",
                DEFAULT_GATES["min_live_success_rate"],
            )
        ),
        "min_dense_hits_avg": float(
            getattr(
                config.settings,
                "benchmark_min_dense_hits_avg",
                DEFAULT_GATES["min_dense_hits_avg"],
            )
        ),
        "min_bm25_hits_avg": float(
            getattr(
                config.settings,
                "benchmark_min_bm25_hits_avg",
                DEFAULT_GATES["min_bm25_hits_avg"],
            )
        ),
        "min_crag_yes_rate_top5": float(
            getattr(
                config.settings,
                "benchmark_min_crag_yes_rate_top5",
                DEFAULT_GATES["min_crag_yes_rate_top5"],
            )
        ),
    }

    cli_overrides = {
        "max_pipeline_ms_avg": args.max_pipeline_ms_avg,
        "max_pipeline_ms_p95": args.max_pipeline_ms_p95,
        "min_live_success_rate": args.min_live_success_rate,
        "min_dense_hits_avg": args.min_dense_hits_avg,
        "min_bm25_hits_avg": args.min_bm25_hits_avg,
        "min_crag_yes_rate_top5": args.min_crag_yes_rate_top5,
    }
    for key, value in cli_overrides.items():
        if value is not None:
            gates[key] = float(value)

    gates.update(_load_gate_overrides(args.gates_config))
    orchestrator = get_orchestrator_service(config=config)
    await orchestrator.initialize()
    reranker = get_reranking_service(config)
    await reranker.initialize()
    grader = get_grader_service(config)
    await grader.initialize()
    expansion_service = QueryExpansionService(config=config, llm_service=orchestrator.llm_service)

    results: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient() as client:
            for idx, question in enumerate(BENCHMARK_QUESTIONS, start=1):
                print(f"[{idx}/10] {question}")
                live = await _call_live_endpoint(
                    client=client,
                    endpoint=full_endpoint,
                    question=question,
                    mode=args.mode,
                    timeout=args.timeout,
                )
                internal = await _collect_internal(
                    orchestrator=orchestrator,
                    reranker=reranker,
                    grader=grader,
                    expansion_service=expansion_service,
                    question=question,
                    mode=args.mode,
                )
                results.append(
                    {
                        "question": question,
                        "live": live,
                        **internal,
                    }
                )
    finally:
        await orchestrator.close()

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved JSON report: {output_path}")

    summary_rows = []
    for item in results:
        latency = item["latency_ms"]
        summary_rows.append(
            [
                _truncate(item["question"], 46),
                str(len(item["expanded_queries"])),
                str(item["dense_count"]),
                str(item["bm25_count"]),
                f"{latency['pipeline_total']:.1f}",
                f"{item['live']['latency_ms']:.1f}",
                "OK" if item["live"]["success"] else "FAIL",
            ]
        )
    headers = ["Question", "Expanded", "Dense", "BM25", "Pipeline ms", "Live ms", "Status"]
    print()
    _print_table(summary_rows, headers)

    if results:
        avg = _build_summary(results)
        print("\nAverages:")
        print(
            "  expanded={expanded:.2f}, dense={dense:.2f}, bm25={bm25:.2f}, "
            "expansion={expansion_ms:.1f}ms, dense={dense_ms:.1f}ms, bm25={bm25_ms:.1f}ms, "
            "rrf={rrf_ms:.1f}ms, rerank={rerank_ms:.1f}ms, grading={grading_ms:.1f}ms, "
            "generation={generation_ms:.1f}ms, pipeline_avg={pipeline_ms_avg:.1f}ms, "
            "pipeline_p95={pipeline_ms_p95:.1f}ms, live={live_ms_avg:.1f}ms, "
            "live_success_rate={live_success_rate:.2%}, crag_yes_rate_top5={crag_yes_rate_top5:.2%}".format(
                **avg
            )
        )

        gates_ok, gate_rows = _evaluate_gates(avg, gates)
        print("\nDoD gates:")
        _print_table(
            gate_rows,
            ["Metric", "Value", "Threshold", "Result"],
        )
        print(f"\nOverall DoD: {'PASS' if gates_ok else 'FAIL'}")

        if args.enforce_gates and not gates_ok:
            raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
