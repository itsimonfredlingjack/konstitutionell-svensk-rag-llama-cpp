#!/usr/bin/env python3
"""
SFS Eval Runner — Measure retrieval hit rate and answer coverage
================================================================

Simpler, SFS-focused eval runner that measures:
- Retrieval hit rate: correct SFS in top-5 results?
- Answer coverage: gold terms present in answer?

Supports --before / --after flags for baseline comparison.
Uses POST /api/constitutional/agent/query endpoint.

Usage:
    python eval/run_eval.py --before                    # Save baseline
    python eval/run_eval.py --after                     # Compare with baseline
    python eval/run_eval.py --category factual_sfs      # Run specific category
    python eval/run_eval.py --backend http://localhost:8900

Note: This is a simpler SFS-focused eval, not a replacement for the existing
eval/eval_runner.py (592 lines) or eval/retrieval_quality_eval.py (739 lines).
"""

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
QUERIES_FILE = EVAL_DIR / "sfs_test_queries.json"
BASELINE_FILE = RESULTS_DIR / "sfs_eval_baseline.json"


def load_queries(category: str | None = None) -> list[dict]:
    """Load test queries from sfs_test_queries.json."""
    with open(QUERIES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    queries = data["queries"]
    if category:
        queries = [q for q in queries if q["category"] == category]

    return queries


def run_query(backend_url: str, query: str, mode: str = "evidence") -> dict:
    """
    Run a single query against the backend.

    Returns dict with 'answer', 'sources', 'latency_ms'.
    """
    url = f"{backend_url}/api/constitutional/agent/query"
    payload = {
        "question": query,
        "mode": mode,
    }

    start = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        result = resp.json()
    except requests.RequestException as e:
        logger.error(f"Query failed: {e}")
        return {"answer": "", "sources": [], "latency_ms": 0, "error": str(e)}

    latency_ms = (time.perf_counter() - start) * 1000

    # Extract answer and sources from response
    answer = result.get("answer", result.get("response", ""))
    sources = result.get("sources", result.get("retrieved_documents", []))

    return {
        "answer": answer,
        "sources": sources,
        "latency_ms": latency_ms,
    }


def check_retrieval_hit(sources: list, expected_sfs: str) -> bool:
    """Check if expected SFS appears in top-5 retrieved sources."""
    if not expected_sfs:
        return True  # No expected SFS = always pass

    for source in sources[:5]:
        source_id = ""
        if isinstance(source, dict):
            source_id = source.get("id", source.get("sfs_nummer", source.get("source", "")))
        elif isinstance(source, str):
            source_id = source

        if expected_sfs in str(source_id):
            return True

    return False


def check_answer_coverage(answer: str, gold_terms: list[str]) -> float:
    """
    Check what fraction of gold terms appear in the answer.

    Returns fraction (0.0 - 1.0).
    """
    if not gold_terms or not answer:
        return 0.0

    answer_lower = answer.lower()
    hits = sum(1 for term in gold_terms if term.lower() in answer_lower)
    return hits / len(gold_terms)


def run_eval(
    backend_url: str = "http://localhost:8900",
    category: str | None = None,
    save_as: str | None = None,
) -> dict:
    """
    Run the full eval suite and return results.

    Args:
        backend_url: Backend URL
        category: Optional category filter
        save_as: "before" or "after" to save/compare baseline

    Returns:
        Dict with overall metrics and per-query results
    """
    queries = load_queries(category)
    logger.info(f"Running {len(queries)} queries against {backend_url}")

    results = []
    total_hit = 0
    total_coverage = 0.0
    total_latency = 0.0

    for i, q in enumerate(queries):
        logger.info(f"[{i + 1}/{len(queries)}] {q['id']}: {q['query'][:60]}...")

        response = run_query(backend_url, q["query"])

        hit = check_retrieval_hit(response["sources"], q["expected_sfs"])
        coverage = check_answer_coverage(response["answer"], q["gold_answer_contains"])

        result = {
            "id": q["id"],
            "category": q["category"],
            "query": q["query"],
            "expected_sfs": q["expected_sfs"],
            "retrieval_hit": hit,
            "answer_coverage": round(coverage, 2),
            "latency_ms": round(response["latency_ms"], 1),
            "answer_preview": response["answer"][:200] if response["answer"] else "",
            "source_count": len(response["sources"]),
            "error": response.get("error"),
        }
        results.append(result)

        total_hit += int(hit)
        total_coverage += coverage
        total_latency += response["latency_ms"]

        # Brief delay to not overwhelm the backend
        time.sleep(0.5)

    n = len(queries)
    summary = {
        "timestamp": datetime.now().isoformat(),
        "backend_url": backend_url,
        "category": category,
        "total_queries": n,
        "retrieval_hit_rate": round(total_hit / n, 3) if n > 0 else 0,
        "mean_answer_coverage": round(total_coverage / n, 3) if n > 0 else 0,
        "mean_latency_ms": round(total_latency / n, 1) if n > 0 else 0,
        "hits": total_hit,
        "misses": n - total_hit,
    }

    # Per-category breakdown
    categories = {q["category"] for q in queries}
    category_breakdown = {}
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_n = len(cat_results)
        cat_hits = sum(1 for r in cat_results if r["retrieval_hit"])
        cat_coverage = sum(r["answer_coverage"] for r in cat_results)
        category_breakdown[cat] = {
            "count": cat_n,
            "hit_rate": round(cat_hits / cat_n, 3) if cat_n > 0 else 0,
            "mean_coverage": round(cat_coverage / cat_n, 3) if cat_n > 0 else 0,
        }

    full_results = {
        "summary": summary,
        "category_breakdown": category_breakdown,
        "results": results,
    }

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if save_as == "before":
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(full_results, f, ensure_ascii=False, indent=2)
        logger.info(f"Baseline saved to {BASELINE_FILE}")
    elif save_as == "after":
        after_file = RESULTS_DIR / f"sfs_eval_after_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(after_file, "w", encoding="utf-8") as f:
            json.dump(full_results, f, ensure_ascii=False, indent=2)
        logger.info(f"After-results saved to {after_file}")

        # Compare with baseline
        if BASELINE_FILE.exists():
            _compare_results(full_results)

    # Always save timestamped copy
    ts_file = RESULTS_DIR / f"sfs_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(ts_file, "w", encoding="utf-8") as f:
        json.dump(full_results, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"SFS Eval Results — {summary['total_queries']} queries")
    print(f"{'=' * 60}")
    print(f"Retrieval hit rate:   {summary['retrieval_hit_rate']:.1%} ({summary['hits']}/{n})")
    print(f"Answer coverage:      {summary['mean_answer_coverage']:.1%}")
    print(f"Mean latency:         {summary['mean_latency_ms']:.0f}ms")
    print()
    for cat, breakdown in category_breakdown.items():
        print(
            f"  {cat}: hit={breakdown['hit_rate']:.0%}, coverage={breakdown['mean_coverage']:.0%} (n={breakdown['count']})"
        )
    print(f"{'=' * 60}\n")

    # Print misses
    misses = [r for r in results if not r["retrieval_hit"]]
    if misses:
        print("MISSES:")
        for m in misses:
            print(f"  {m['id']}: expected {m['expected_sfs']} — {m['query'][:50]}...")
        print()

    return full_results


def _compare_results(after_results: dict):
    """Compare after results with baseline."""
    with open(BASELINE_FILE, encoding="utf-8") as f:
        baseline = json.load(f)

    before = baseline["summary"]
    after = after_results["summary"]

    print(f"\n{'=' * 60}")
    print("COMPARISON: Before → After")
    print(f"{'=' * 60}")

    hit_delta = after["retrieval_hit_rate"] - before["retrieval_hit_rate"]
    cov_delta = after["mean_answer_coverage"] - before["mean_answer_coverage"]
    lat_delta = after["mean_latency_ms"] - before["mean_latency_ms"]

    hit_arrow = "+" if hit_delta > 0 else ""
    cov_arrow = "+" if cov_delta > 0 else ""
    lat_arrow = "+" if lat_delta > 0 else ""

    print(
        f"Hit rate:    {before['retrieval_hit_rate']:.1%} → {after['retrieval_hit_rate']:.1%} ({hit_arrow}{hit_delta:.1%})"
    )
    print(
        f"Coverage:    {before['mean_answer_coverage']:.1%} → {after['mean_answer_coverage']:.1%} ({cov_arrow}{cov_delta:.1%})"
    )
    print(
        f"Latency:     {before['mean_latency_ms']:.0f}ms → {after['mean_latency_ms']:.0f}ms ({lat_arrow}{lat_delta:.0f}ms)"
    )
    print(f"{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(description="SFS Eval Runner")
    parser.add_argument("--backend", default="http://localhost:8900", help="Backend URL")
    parser.add_argument(
        "--category", type=str, help="Filter by category (factual_sfs, cross_reference, reasoning)"
    )
    parser.add_argument("--before", action="store_true", help="Save as baseline (before changes)")
    parser.add_argument("--after", action="store_true", help="Save and compare with baseline")
    args = parser.parse_args()

    save_as = None
    if args.before:
        save_as = "before"
    elif args.after:
        save_as = "after"

    run_eval(
        backend_url=args.backend,
        category=args.category,
        save_as=save_as,
    )


if __name__ == "__main__":
    main()
