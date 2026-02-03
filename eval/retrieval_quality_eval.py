#!/usr/bin/env python3
"""
Retrieval Quality Evaluation Suite
==================================

Diagnostik-fokuserad evaluering av retrieval-pipelinen.
Mäter source counts, score-distribution, latency, recall@K och query expansion.

Till skillnad från eval_runner.py som fokuserar på svarskvalitet (faithfulness, relevancy),
fokuserar denna modul på retrieval-kvalitet och diagnostik.

Användning:
    python eval/retrieval_quality_eval.py           # CLI-körning
    pytest eval/retrieval_quality_eval.py -v -s     # pytest-körning

Output:
    - JSON: eval/results/retrieval_eval_YYYYMMDD_HHMMSS.json
    - Markdown: eval/results/retrieval_eval_YYYYMMDD_HHMMSS.md
"""

import asyncio
import json
import logging
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
import httpx
import pytest
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

# Setup
console = Console()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
EVAL_DIR = Path(__file__).parent
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# API endpoint for health check
BACKEND_URL = "http://localhost:8900"
HEALTH_ENDPOINT = f"{BACKEND_URL}/api/constitutional/health"

# SFS alias mapping for recall matching
SFS_ALIASES = {
    "RF": "1974:152",
    "TF": "1949:105",
    "YGL": "1991:1469",
    "OSL": "2009:400",
    "FL": "2017:900",
    "FPL": "1971:291",
    "KL": "2017:725",
    "BrB": "1962:700",
    "PBL": "2010:900",
}


# ═══════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class GroundTruthDoc:
    """A ground truth document specification."""

    doc_type: str  # "sfs", "proposition"
    identifier: str  # "1974:152"
    partial_match: bool = True  # Match identifier in snippet/id/source


@dataclass
class EvalQuestion:
    """An evaluation question with ground truth."""

    id: str
    query: str
    category: str  # FAKTAFRAGOR, JAMFORELSEFRAGOR, TEMPORALA_FRAGOR
    ground_truth_docs: list[GroundTruthDoc]
    description: str = ""


@dataclass
class RetrievalMetricsResult:
    """Result metrics for a single question."""

    question_id: str
    query: str
    category: str

    # Source counts
    sources_before_filters: int = 0
    sources_after_reranking: int = 0
    sources_final: int = 0

    # Score distribution
    score_min: float = 0.0
    score_max: float = 0.0
    score_median: float = 0.0
    score_stddev: float = 0.0

    # Latency
    retrieval_latency_ms: float = 0.0

    # Recall
    recall_at_5: bool = False
    ground_truth_rank: int | None = None
    ground_truth_found: bool = False

    # Query expansion
    query_variants: list[str] = field(default_factory=list)
    fusion_gain: float = 0.0

    # Escalation
    escalation_path: list[str] = field(default_factory=list)
    fallback_triggered: bool = False

    # Debug
    top_5_doc_ids: list[str] = field(default_factory=list)
    top_5_scores: list[float] = field(default_factory=list)

    # Error
    error: str | None = None


@dataclass
class EvaluationReport:
    """Complete evaluation report."""

    timestamp: str
    version: str = "1.0-retrieval"
    total_questions: int = 0
    recall_at_5_rate: float = 0.0
    avg_latency_ms: float = 0.0
    zero_source_count: int = 0
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)
    problems: dict[str, list[str]] = field(default_factory=dict)
    results: list[RetrievalMetricsResult] = field(default_factory=list)

    @property
    def zero_source_questions(self) -> list[str]:
        """Return list of question IDs with zero sources."""
        return self.problems.get("zero_sources", [])


# ═══════════════════════════════════════════════════════════════════════════
# EVALUATOR
# ═══════════════════════════════════════════════════════════════════════════


class RetrievalQualityEvaluator:
    """Main evaluator for retrieval quality."""

    def __init__(self):
        self.questions: list[EvalQuestion] = []
        self.chromadb_client = None
        self.embedding_service = None
        self.retrieval_orchestrator = None
        self._http_client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Initialize services and verify backend health."""
        console.print("[cyan]Initializing retrieval quality evaluator...[/cyan]")

        # Health check backend
        self._http_client = httpx.AsyncClient(timeout=30.0)
        try:
            response = await self._http_client.get(HEALTH_ENDPOINT)
            if response.status_code != 200:
                raise RuntimeError(f"Backend health check failed: {response.status_code}")
            health = response.json()
            console.print(f"[green]Backend healthy: {health.get('status', 'unknown')}[/green]")
        except httpx.ConnectError as e:
            raise RuntimeError(
                f"Cannot connect to backend at {BACKEND_URL}. Is it running? Error: {e}"
            ) from e

        # Initialize ChromaDB
        sys.path.insert(0, str(BASE_DIR / "backend"))
        from app.services.config_service import get_config_service
        from app.services.embedding_service import get_embedding_service
        from app.services.query_rewriter import QueryRewriter
        from app.services.rag_fusion import QueryExpander
        from app.services.retrieval_orchestrator import RetrievalOrchestrator

        config = get_config_service()

        console.print(f"[dim]ChromaDB path: {config.chromadb_path}[/dim]")
        self.chromadb_client = chromadb.PersistentClient(path=config.chromadb_path)

        # Initialize embedding service
        self.embedding_service = get_embedding_service(config)
        console.print(f"[dim]Embedding model: {config.embedding_model}[/dim]")

        # Initialize query rewriter and expander
        query_rewriter = QueryRewriter()
        query_expander = QueryExpander(max_queries=3)

        # Initialize retrieval orchestrator
        self.retrieval_orchestrator = RetrievalOrchestrator(
            chromadb_client=self.chromadb_client,
            embedding_function=self.embedding_service.embed,
            default_timeout=config.search_timeout,
            query_rewriter=query_rewriter,
            query_expander=query_expander,
            default_collections=config.effective_default_collections,
            rrf_k=config.rrf_k,
        )

        console.print("[green]Evaluator initialized successfully[/green]")

    def load_ground_truth(self) -> None:
        """Load test questions from ground_truth.json."""
        if not GROUND_TRUTH_PATH.exists():
            raise FileNotFoundError(f"Ground truth file not found: {GROUND_TRUTH_PATH}")

        with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
            data = json.load(f)

        self.questions = []
        for q in data["questions"]:
            ground_truth_docs = [
                GroundTruthDoc(
                    doc_type=d["doc_type"],
                    identifier=d["identifier"],
                    partial_match=d.get("partial_match", True),
                )
                for d in q["ground_truth_docs"]
            ]
            self.questions.append(
                EvalQuestion(
                    id=q["id"],
                    query=q["query"],
                    category=q["category"],
                    ground_truth_docs=ground_truth_docs,
                    description=q.get("description", ""),
                )
            )

        console.print(f"[dim]Loaded {len(self.questions)} test questions[/dim]")

    async def evaluate_single_question(self, question: EvalQuestion) -> RetrievalMetricsResult:
        """Evaluate retrieval for a single question."""
        result = RetrievalMetricsResult(
            question_id=question.id,
            query=question.query,
            category=question.category,
        )

        try:
            start_time = time.perf_counter()

            # Call retrieval orchestrator with EPR routing
            retrieval_result = await self.retrieval_orchestrator.search_with_routing(
                query=question.query,
                k=10,
                history=None,
            )

            result.retrieval_latency_ms = (time.perf_counter() - start_time) * 1000

            if not retrieval_result.success:
                result.error = retrieval_result.error
                return result

            # Extract metrics from retrieval result
            search_results = retrieval_result.results
            metrics = retrieval_result.metrics

            result.sources_final = len(search_results)
            result.sources_before_filters = metrics.dense_result_count + metrics.bm25_result_count
            result.sources_after_reranking = metrics.unique_docs_total

            # Score distribution
            if search_results:
                scores = [r.score for r in search_results]
                result.score_min = min(scores)
                result.score_max = max(scores)
                result.score_median = statistics.median(scores)
                result.score_stddev = statistics.stdev(scores) if len(scores) > 1 else 0.0

                # Top 5 debug info
                result.top_5_doc_ids = [r.id for r in search_results[:5]]
                result.top_5_scores = [r.score for r in search_results[:5]]

            # Query expansion metrics
            if metrics.fusion_used:
                result.query_variants = metrics.query_variants
                result.fusion_gain = metrics.fusion_gain

            # Escalation metrics (from adaptive)
            if metrics.escalation_path:
                result.escalation_path = metrics.escalation_path
                result.fallback_triggered = metrics.fallback_triggered

            # Check recall
            result.recall_at_5, result.ground_truth_rank, result.ground_truth_found = (
                self._check_recall(search_results, question.ground_truth_docs)
            )

        except Exception as e:
            result.error = str(e)
            logger.error(f"Error evaluating {question.id}: {e}")

        return result

    def _check_recall(
        self, results: list, ground_truth_docs: list[GroundTruthDoc]
    ) -> tuple[bool, int | None, bool]:
        """
        Check if ground truth documents are found in results.

        Returns:
            (recall_at_5, ground_truth_rank, ground_truth_found)
        """
        if not results or not ground_truth_docs:
            return False, None, False

        # Build search targets including aliases
        search_identifiers = set()
        for gt_doc in ground_truth_docs:
            search_identifiers.add(gt_doc.identifier)
            # Add alias if exists
            for alias, sfs_num in SFS_ALIASES.items():
                if sfs_num == gt_doc.identifier:
                    search_identifiers.add(alias)

        # Search in results
        found_rank = None
        for i, r in enumerate(results):
            # Build searchable text from result
            searchable = f"{r.id} {r.source} {r.snippet}".lower()

            for identifier in search_identifiers:
                if identifier.lower() in searchable:
                    if found_rank is None:
                        found_rank = i + 1  # 1-indexed rank
                    break

            if found_rank is not None:
                break

        recall_at_5 = found_rank is not None and found_rank <= 5
        ground_truth_found = found_rank is not None

        return recall_at_5, found_rank, ground_truth_found

    async def run_evaluation(self) -> EvaluationReport:
        """Run evaluation on all questions."""
        self.load_ground_truth()

        results: list[RetrievalMetricsResult] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Running retrieval evaluation...", total=len(self.questions)
            )

            for question in self.questions:
                result = await self.evaluate_single_question(question)
                results.append(result)
                progress.update(task, advance=1)

        # Build report
        report = self._build_report(results)
        return report

    def _build_report(self, results: list[RetrievalMetricsResult]) -> EvaluationReport:
        """Build evaluation report from results."""
        report = EvaluationReport(
            timestamp=datetime.now().isoformat(),
            total_questions=len(results),
            results=results,
        )

        # Calculate aggregates
        valid_results = [r for r in results if r.error is None]

        if valid_results:
            report.recall_at_5_rate = sum(1 for r in valid_results if r.recall_at_5) / len(
                valid_results
            )
            report.avg_latency_ms = sum(r.retrieval_latency_ms for r in valid_results) / len(
                valid_results
            )

        # Count problems
        zero_sources = [r.question_id for r in results if r.sources_final == 0]
        missed_ground_truth = [r.question_id for r in valid_results if not r.ground_truth_found]
        slow_queries = [r.question_id for r in valid_results if r.retrieval_latency_ms > 2000]
        low_separation = [
            r.question_id
            for r in valid_results
            if r.score_max > 0 and r.score_stddev < 0.05 and r.sources_final > 1
        ]

        report.problems = {
            "zero_sources": zero_sources,
            "missed_ground_truth": missed_ground_truth,
            "slow_queries": slow_queries,
            "low_separation": low_separation,
        }
        report.zero_source_count = len(zero_sources)

        # Group by category
        categories = {}
        for r in results:
            cat = r.category
            if cat not in categories:
                categories[cat] = {"total": 0, "recall_at_5": 0, "avg_latency_ms": 0.0}
            categories[cat]["total"] += 1
            if r.recall_at_5:
                categories[cat]["recall_at_5"] += 1
            categories[cat]["avg_latency_ms"] += r.retrieval_latency_ms

        for _cat, stats in categories.items():
            if stats["total"] > 0:
                stats["recall_at_5_rate"] = stats["recall_at_5"] / stats["total"]
                stats["avg_latency_ms"] = stats["avg_latency_ms"] / stats["total"]

        report.by_category = categories

        return report

    async def close(self) -> None:
        """Cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════


class ReportGenerator:
    """Generate JSON and Markdown reports."""

    def generate_json_report(self, report: EvaluationReport) -> Path:
        """Generate JSON report file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = RESULTS_DIR / f"retrieval_eval_{timestamp}.json"

        # Convert to dict
        report_dict = {
            "metadata": {
                "timestamp": report.timestamp,
                "version": report.version,
            },
            "summary": {
                "total_questions": report.total_questions,
                "recall_at_5_rate": round(report.recall_at_5_rate, 4),
                "avg_latency_ms": round(report.avg_latency_ms, 2),
                "zero_source_count": report.zero_source_count,
            },
            "by_category": report.by_category,
            "problems": report.problems,
            "results": [asdict(r) for r in report.results],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)

        return filepath

    def generate_markdown_report(self, report: EvaluationReport) -> Path:
        """Generate Markdown report file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = RESULTS_DIR / f"retrieval_eval_{timestamp}.md"

        lines = [
            "# Retrieval Quality Evaluation Report",
            "",
            f"**Generated:** {report.timestamp}",
            f"**Version:** {report.version}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Questions | {report.total_questions} |",
            f"| Recall@5 Rate | {report.recall_at_5_rate:.1%} |",
            f"| Avg Latency | {report.avg_latency_ms:.0f}ms |",
            f"| Zero Sources | {report.zero_source_count} |",
            "",
            "## Results by Category",
            "",
            "| Category | Total | Recall@5 | Avg Latency |",
            "|----------|-------|----------|-------------|",
        ]

        for cat, stats in report.by_category.items():
            recall_rate = stats.get("recall_at_5_rate", 0)
            avg_lat = stats.get("avg_latency_ms", 0)
            lines.append(f"| {cat} | {stats['total']} | {recall_rate:.1%} | {avg_lat:.0f}ms |")

        lines.extend(
            [
                "",
                "## Problems",
                "",
            ]
        )

        if report.problems.get("zero_sources"):
            lines.append(f"### Zero Sources ({len(report.problems['zero_sources'])})")
            for qid in report.problems["zero_sources"]:
                lines.append(f"- {qid}")
            lines.append("")

        if report.problems.get("missed_ground_truth"):
            lines.append(f"### Missed Ground Truth ({len(report.problems['missed_ground_truth'])})")
            for qid in report.problems["missed_ground_truth"]:
                lines.append(f"- {qid}")
            lines.append("")

        if report.problems.get("slow_queries"):
            lines.append(f"### Slow Queries >2s ({len(report.problems['slow_queries'])})")
            for qid in report.problems["slow_queries"]:
                lines.append(f"- {qid}")
            lines.append("")

        if report.problems.get("low_separation"):
            lines.append(f"### Low Score Separation ({len(report.problems['low_separation'])})")
            for qid in report.problems["low_separation"]:
                lines.append(f"- {qid}")
            lines.append("")

        # Actionable recommendations
        lines.extend(
            [
                "## Recommendations",
                "",
            ]
        )

        if report.recall_at_5_rate < 0.7:
            lines.append(
                "- **Low Recall@5**: Consider tuning reranking thresholds or expanding query variants"
            )

        if report.zero_source_count > 2:
            lines.append(
                "- **Zero Sources**: Check collection coverage and minimum score threshold"
            )

        if report.avg_latency_ms > 1500:
            lines.append("- **High Latency**: Review parallel search configuration and timeouts")

        if len(report.problems.get("low_separation", [])) > 3:
            lines.append(
                "- **Low Score Separation**: Documents may be too similar; consider chunking strategy"
            )

        lines.append("")

        # Individual results table
        lines.extend(
            [
                "## Individual Results",
                "",
                "| ID | Category | Recall@5 | Rank | Sources | Latency |",
                "|----|----------|----------|------|---------|---------|",
            ]
        )

        for r in report.results:
            recall_icon = "✓" if r.recall_at_5 else "✗"
            rank = str(r.ground_truth_rank) if r.ground_truth_rank else "-"
            lines.append(
                f"| {r.question_id} | {r.category[:8]} | {recall_icon} | {rank} | "
                f"{r.sources_final} | {r.retrieval_latency_ms:.0f}ms |"
            )

        lines.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return filepath


def print_console_report(report: EvaluationReport) -> None:
    """Print report to console using Rich."""
    console.print()
    console.print(
        Panel(
            f"[bold]Retrieval Quality Evaluation Report[/bold]\n"
            f"Version: {report.version} | {report.timestamp}",
            border_style="blue",
        )
    )

    # Summary
    console.print()
    recall_color = "green" if report.recall_at_5_rate >= 0.7 else "red"
    console.print(
        f"[bold]Questions:[/bold] {report.total_questions} | "
        f"[{recall_color}]Recall@5:[/{recall_color}] {report.recall_at_5_rate:.1%} | "
        f"[cyan]Avg Latency:[/cyan] {report.avg_latency_ms:.0f}ms | "
        f"[yellow]Zero Sources:[/yellow] {report.zero_source_count}"
    )

    # By category table
    console.print()
    cat_table = Table(title="Results by Category", box=box.ROUNDED)
    cat_table.add_column("Category", style="cyan")
    cat_table.add_column("Total", justify="right")
    cat_table.add_column("Recall@5", justify="right")
    cat_table.add_column("Avg Latency", justify="right")

    for cat, stats in sorted(report.by_category.items()):
        recall_rate = stats.get("recall_at_5_rate", 0)
        recall_style = "green" if recall_rate >= 0.7 else "red"
        cat_table.add_row(
            cat,
            str(stats["total"]),
            f"[{recall_style}]{recall_rate:.0%}[/{recall_style}]",
            f"{stats.get('avg_latency_ms', 0):.0f}ms",
        )

    console.print(cat_table)

    # Problems
    if any(report.problems.values()):
        console.print()
        console.print("[bold red]Problems Found:[/bold red]")

        if report.problems.get("zero_sources"):
            console.print(f"  • Zero sources: {', '.join(report.problems['zero_sources'])}")

        if report.problems.get("missed_ground_truth"):
            console.print(
                f"  • Missed ground truth: {', '.join(report.problems['missed_ground_truth'][:5])}"
                + ("..." if len(report.problems["missed_ground_truth"]) > 5 else "")
            )

        if report.problems.get("slow_queries"):
            console.print(f"  • Slow queries: {', '.join(report.problems['slow_queries'])}")


# ═══════════════════════════════════════════════════════════════════════════
# PYTEST INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.slow
async def test_retrieval_quality():
    """
    Pytest integration test for retrieval quality.

    Asserts:
        - Recall@5 >= 70%
        - Max 2 questions with zero sources
    """
    evaluator = RetrievalQualityEvaluator()
    try:
        await evaluator.initialize()
        report = await evaluator.run_evaluation()

        # Generate reports
        generator = ReportGenerator()
        json_path = generator.generate_json_report(report)
        md_path = generator.generate_markdown_report(report)

        # Print console report
        print_console_report(report)

        console.print(f"\n[dim]JSON report: {json_path}[/dim]")
        console.print(f"[dim]Markdown report: {md_path}[/dim]")

        # Assertions
        assert (
            report.recall_at_5_rate >= 0.7
        ), f"Recall@5 rate {report.recall_at_5_rate:.1%} < 70% threshold"

        assert (
            len(report.zero_source_questions) <= 2
        ), f"Too many zero-source questions: {report.zero_source_questions}"

    finally:
        await evaluator.close()


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


async def main():
    """CLI entry point."""
    console.print("[bold]Retrieval Quality Evaluation Suite[/bold]")
    console.print()

    evaluator = RetrievalQualityEvaluator()
    try:
        await evaluator.initialize()
        report = await evaluator.run_evaluation()

        # Generate reports
        generator = ReportGenerator()
        json_path = generator.generate_json_report(report)
        md_path = generator.generate_markdown_report(report)

        # Print console report
        print_console_report(report)

        console.print(f"\n[dim]JSON report saved: {json_path}[/dim]")
        console.print(f"[dim]Markdown report saved: {md_path}[/dim]")

        # Exit code based on recall rate
        return 0 if report.recall_at_5_rate >= 0.7 else 1

    finally:
        await evaluator.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
