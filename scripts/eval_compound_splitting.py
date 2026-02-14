#!/usr/bin/env python3
"""
A/B Test: Swedish Compound Splitting Recall Improvement
========================================================

Compares BM25 search recall WITH vs WITHOUT compound splitting
to validate Gemini's claimed 64% recall improvement.

Usage:
    python scripts/eval_compound_splitting.py

Output:
    - Recall@10, Recall@20, MRR, Hit Rate metrics
    - Per-category breakdown
    - Percentage improvement comparison
"""

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.bm25_service import get_bm25_service


@dataclass
class QueryResult:
    """Result for a single query."""

    query_id: str
    query: str
    category: str
    expected_patterns: list[str]
    hits_with: list[dict[str, Any]] = field(default_factory=list)
    hits_without: list[dict[str, Any]] = field(default_factory=list)
    recall_at_10_with: float = 0.0
    recall_at_10_without: float = 0.0
    recall_at_20_with: float = 0.0
    recall_at_20_without: float = 0.0
    mrr_with: float = 0.0
    mrr_without: float = 0.0


@dataclass
class CategoryMetrics:
    """Aggregated metrics for a category."""

    count: int = 0
    recall_10_with: float = 0.0
    recall_10_without: float = 0.0
    recall_20_with: float = 0.0
    recall_20_without: float = 0.0
    mrr_with: float = 0.0
    mrr_without: float = 0.0
    hit_rate_with: float = 0.0
    hit_rate_without: float = 0.0


class CompoundSplittingEvaluator:
    """A/B test evaluator for compound splitting."""

    def __init__(self, test_file: Path):
        self.test_file = test_file
        self.bm25 = get_bm25_service()
        self.results: list[QueryResult] = []

    def load_test_queries(self) -> list[dict]:
        """Load test queries from JSON file."""
        with open(self.test_file) as f:
            data = json.load(f)
        return data.get("compound_queries", [])

    def pattern_in_results(self, pattern: str, results: list[dict], k: int = 10) -> bool:
        """Check if pattern appears in top-k results."""
        pattern_lower = pattern.lower()
        for result in results[:k]:
            # Check in document text if available
            text = result.get("text", "")
            doc_id = result.get("id", "")
            if pattern_lower in text.lower() or pattern_lower in doc_id.lower():
                return True
        return False

    def find_pattern_rank(self, pattern: str, results: list[dict]) -> int:
        """Find rank of first result containing pattern (1-indexed, 0 if not found)."""
        pattern_lower = pattern.lower()
        for i, result in enumerate(results):
            text = result.get("text", "")
            doc_id = result.get("id", "")
            if pattern_lower in text.lower() or pattern_lower in doc_id.lower():
                return i + 1
        return 0

    def calc_recall_at_k(self, results: list[dict], expected: list[str], k: int) -> float:
        """Calculate recall@k: fraction of expected patterns found in top-k."""
        if not expected:
            return 0.0
        found = sum(1 for pat in expected if self.pattern_in_results(pat, results, k))
        return found / len(expected)

    def calc_mrr(self, results: list[dict], expected: list[str]) -> float:
        """Calculate Mean Reciprocal Rank for first expected pattern found."""
        if not expected:
            return 0.0
        # Find rank of first expected pattern
        best_rank = float("inf")
        for pat in expected:
            rank = self.find_pattern_rank(pat, results)
            if rank > 0 and rank < best_rank:
                best_rank = rank
        return 1.0 / best_rank if best_rank != float("inf") else 0.0

    def run_single_query(self, query_data: dict) -> QueryResult:
        """Run A/B test for a single query."""
        query_id = query_data.get("id", "unknown")
        query = query_data.get("query", "")
        category = query_data.get("category", "unknown")
        expected = query_data.get("expected_doc_patterns", [])

        # Search WITH compound splitting
        hits_with = self.bm25.search(
            query=query,
            k=50,
            return_docs=True,
            use_compound_splitting=True,
        )

        # Search WITHOUT compound splitting
        hits_without = self.bm25.search(
            query=query,
            k=50,
            return_docs=True,
            use_compound_splitting=False,
        )

        result = QueryResult(
            query_id=query_id,
            query=query,
            category=category,
            expected_patterns=expected,
            hits_with=hits_with,
            hits_without=hits_without,
        )

        # Calculate metrics
        result.recall_at_10_with = self.calc_recall_at_k(hits_with, expected, 10)
        result.recall_at_10_without = self.calc_recall_at_k(hits_without, expected, 10)
        result.recall_at_20_with = self.calc_recall_at_k(hits_with, expected, 20)
        result.recall_at_20_without = self.calc_recall_at_k(hits_without, expected, 20)
        result.mrr_with = self.calc_mrr(hits_with, expected)
        result.mrr_without = self.calc_mrr(hits_without, expected)

        return result

    def run_ab_test(self) -> dict[str, Any]:
        """Run full A/B test on all queries."""
        queries = self.load_test_queries()
        print(f"Loaded {len(queries)} test queries")
        print()

        # Ensure BM25 index is loaded
        if not self.bm25.is_available():
            print("ERROR: BM25 index not available!")
            return {}

        print("Running A/B test...")
        for i, query_data in enumerate(queries):
            result = self.run_single_query(query_data)
            self.results.append(result)

            # Progress indicator
            status = "✓" if result.recall_at_10_with >= result.recall_at_10_without else "○"
            print(
                f"  [{i + 1:02d}/{len(queries)}] {status} {result.query_id}: "
                f"R@10 {result.recall_at_10_with:.0%} vs {result.recall_at_10_without:.0%}"
            )

        return self.aggregate_results()

    def aggregate_results(self) -> dict[str, Any]:
        """Aggregate results across all queries and categories."""
        if not self.results:
            return {}

        # Overall metrics
        n = len(self.results)
        overall = {
            "count": n,
            "recall_10_with": sum(r.recall_at_10_with for r in self.results) / n,
            "recall_10_without": sum(r.recall_at_10_without for r in self.results) / n,
            "recall_20_with": sum(r.recall_at_20_with for r in self.results) / n,
            "recall_20_without": sum(r.recall_at_20_without for r in self.results) / n,
            "mrr_with": sum(r.mrr_with for r in self.results) / n,
            "mrr_without": sum(r.mrr_without for r in self.results) / n,
            "hit_rate_with": sum(1 for r in self.results if r.recall_at_10_with > 0) / n,
            "hit_rate_without": sum(1 for r in self.results if r.recall_at_10_without > 0) / n,
        }

        # Per-category metrics
        by_category: dict[str, CategoryMetrics] = defaultdict(CategoryMetrics)
        for r in self.results:
            cat = by_category[r.category]
            cat.count += 1
            cat.recall_10_with += r.recall_at_10_with
            cat.recall_10_without += r.recall_at_10_without
            cat.recall_20_with += r.recall_at_20_with
            cat.recall_20_without += r.recall_at_20_without
            cat.mrr_with += r.mrr_with
            cat.mrr_without += r.mrr_without
            cat.hit_rate_with += 1 if r.recall_at_10_with > 0 else 0
            cat.hit_rate_without += 1 if r.recall_at_10_without > 0 else 0

        # Average per category
        categories = {}
        for cat_name, cat in by_category.items():
            if cat.count > 0:
                categories[cat_name] = {
                    "count": cat.count,
                    "recall_10_with": cat.recall_10_with / cat.count,
                    "recall_10_without": cat.recall_10_without / cat.count,
                    "improvement": self._calc_improvement(
                        cat.recall_10_with / cat.count,
                        cat.recall_10_without / cat.count,
                    ),
                }

        return {"overall": overall, "categories": categories}

    def _calc_improvement(self, with_val: float, without_val: float) -> float:
        """Calculate percentage improvement."""
        if without_val == 0:
            return float("inf") if with_val > 0 else 0.0
        return (with_val - without_val) / without_val

    def print_report(self, results: dict[str, Any]) -> None:
        """Print formatted A/B test report."""
        if not results:
            print("No results to report")
            return

        overall = results["overall"]
        categories = results["categories"]

        print()
        print("=" * 60)
        print("COMPOUND SPLITTING A/B TEST RESULTS")
        print("=" * 60)
        print(f"Queries tested: {overall['count']}")
        cat_summary = ", ".join(f"{k}({v['count']})" for k, v in categories.items())
        print(f"Categories: {cat_summary}")
        print()

        # WITH compound splitting
        print("WITH compound splitting:")
        print(f"  Recall@10:  {overall['recall_10_with']:6.1%}")
        print(f"  Recall@20:  {overall['recall_20_with']:6.1%}")
        print(f"  MRR:        {overall['mrr_with']:6.2f}")
        print(f"  Hit Rate:   {overall['hit_rate_with']:6.1%}")
        print()

        # WITHOUT compound splitting
        print("WITHOUT compound splitting:")
        print(f"  Recall@10:  {overall['recall_10_without']:6.1%}")
        print(f"  Recall@20:  {overall['recall_20_without']:6.1%}")
        print(f"  MRR:        {overall['mrr_without']:6.2f}")
        print(f"  Hit Rate:   {overall['hit_rate_without']:6.1%}")
        print()

        # Improvement
        r10_imp = self._calc_improvement(overall["recall_10_with"], overall["recall_10_without"])
        r20_imp = self._calc_improvement(overall["recall_20_with"], overall["recall_20_without"])
        mrr_imp = self._calc_improvement(overall["mrr_with"], overall["mrr_without"])
        hr_imp = self._calc_improvement(overall["hit_rate_with"], overall["hit_rate_without"])

        print("IMPROVEMENT:")
        print(
            f"  Recall@10:  {r10_imp:+6.1%} {'⬆️' if r10_imp > 0 else '⬇️' if r10_imp < 0 else '─'}"
        )
        print(
            f"  Recall@20:  {r20_imp:+6.1%} {'⬆️' if r20_imp > 0 else '⬇️' if r20_imp < 0 else '─'}"
        )
        print(
            f"  MRR:        {mrr_imp:+6.1%} {'⬆️' if mrr_imp > 0 else '⬇️' if mrr_imp < 0 else '─'}"
        )
        print(f"  Hit Rate:   {hr_imp:+6.1%} {'⬆️' if hr_imp > 0 else '⬇️' if hr_imp < 0 else '─'}")
        print()

        # Per-category breakdown
        print("Per-category breakdown:")
        for cat_name, cat_data in sorted(categories.items()):
            imp = cat_data["improvement"]
            arrow = "⬆️" if imp > 0 else "⬇️" if imp < 0 else "─"
            print(f"  {cat_name:12s}: {imp:+6.1%} recall improvement {arrow}")

        print("=" * 60)

        # Gemini comparison
        print()
        if r10_imp > 0:
            print(f"📊 Result: {r10_imp:+.1%} recall improvement (Gemini claimed +64%)")
            if r10_imp >= 0.5:
                print("✅ Validates significant improvement from compound splitting!")
            elif r10_imp >= 0.3:
                print("✅ Substantial improvement, slightly below Gemini's estimate")
            else:
                print("⚠️  Lower than expected - may depend on corpus/query types")
        else:
            print("⚠️  No improvement detected - check test queries and index")


def main():
    """Run A/B test evaluation."""
    test_file = Path(__file__).parent.parent / "tools/rag-tester/data/compound_test_queries.json"

    if not test_file.exists():
        print(f"ERROR: Test file not found: {test_file}")
        sys.exit(1)

    evaluator = CompoundSplittingEvaluator(test_file)
    results = evaluator.run_ab_test()
    evaluator.print_report(results)


if __name__ == "__main__":
    main()
