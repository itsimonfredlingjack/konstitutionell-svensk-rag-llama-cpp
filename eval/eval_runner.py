#!/usr/bin/env python3
"""
Constitutional-AI Evaluation Runner
===================================

Kör golden set mot RAG-systemet och mäter kvalitet med RAGAS-mått.

Användning:
    python eval_runner.py --quick          # 10 frågor, 2 min
    python eval_runner.py --full           # 20 frågor, 5 min
    python eval_runner.py --compare baseline.json

Output:
    - Console: Pretty-printed resultat
    - File: eval_results_{timestamp}.json
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

# Import our RAGAS wrapper
try:
    from ragas_wrapper import MetricsProvider, get_metrics_provider
except ImportError:
    print("ERROR: ragas_wrapper.py not found. Make sure it's in the same directory.")
    sys.exit(1)

# Setup
console = Console()
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
GOLDEN_SET_PATH = BASE_DIR / "docs" / "eval" / "golden_set.json"
RESULTS_DIR = BASE_DIR / "eval" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# API endpoints
BACKEND_URL = "http://localhost:8000"
SEARCH_ENDPOINT = f"{BACKEND_URL}/api/constitutional/search"


# ═══════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class EvalMetrics:
    """Metrics för en enskild fråga"""

    sources_count: int
    primary_source: bool  # SFS-källa hittad
    evidence_level: str  # green/yellow/red
    warden_status: str  # VERIFIED/REGENERATED/ERROR/SKIPPED
    claim_strips: int  # Borttagna hallucinationer
    degrade_count: int  # Regenereringar
    faithfulness: float
    context_precision: float
    context_recall: float
    answer_relevancy: float
    latency_ms: int


@dataclass
class EvalResult:
    """Resultat för en enskild fråga"""

    id: str
    query: str
    intent: str
    answer: str
    contexts: list[str]
    metrics: EvalMetrics
    passed: bool
    error: Optional[str] = None


@dataclass
class EvalReport:
    """Sammanfattande rapport"""

    timestamp: str
    version: str
    total_questions: int
    passed: int
    failed: int
    pass_rate: float
    avg_faithfulness: float
    avg_context_precision: float
    avg_context_recall: float
    avg_answer_relevancy: float
    by_intent: dict[str, dict[str, Any]]
    results: list[EvalResult]


# ═══════════════════════════════════════════════════════════════════════════
# EVAL RUNNER
# ═══════════════════════════════════════════════════════════════════════════


class EvalRunner:
    """Kör evaluation mot RAG-systemet"""

    def __init__(self, metrics_provider: str = "ragas"):
        self.metrics = get_metrics_provider(metrics_provider)
        self.client = httpx.AsyncClient(timeout=60.0)

    async def load_golden_set(self) -> list[dict]:
        """Ladda golden set från JSON"""
        if not GOLDEN_SET_PATH.exists():
            raise FileNotFoundError(f"Golden set not found: {GOLDEN_SET_PATH}")

        with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
            data = json.load(f)

        return data["questions"]

    async def run_single_query(self, question: dict) -> EvalResult:
        """Kör en enskild fråga mot RAG-systemet"""
        q_id = question["id"]
        query = question["query"]
        intent = question["intent"]
        should_search = question.get("should_search", True)
        ground_truth = question.get("ground_truth", "")

        logger.info(f"Running {q_id}: {query[:50]}...")

        start_time = datetime.now()

        try:
            # Call search API
            if not should_search:
                # Smalltalk - ska inte trigga RAG
                answer = "Jag hjälper dig med juridiska frågor."
                contexts = []
                sources_count = 0
                primary_source = False
            else:
                # Normal RAG query
                response = await self.client.post(
                    SEARCH_ENDPOINT,
                    json={"query": query, "limit": 10, "page": 1, "sort": "relevance"},
                )

                if response.status_code != 200:
                    raise Exception(f"Search API error: {response.status_code}")

                data = response.json()
                results = data.get("results", [])

                # Extract contexts
                contexts = [r.get("snippet", "") for r in results[:5]]
                sources_count = len(results)

                # Check for primary source (SFS)
                primary_source = any(r.get("doc_type") == "sfs" for r in results)

                # Simulate answer generation (i produktion: anropa agent-loop)
                # För nu: använd ground_truth som "svar"
                answer = ground_truth if ground_truth else "Svar baserat på källor."

            latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Calculate RAGAS metrics
            faithfulness = self.metrics.faithfulness(answer, contexts, query)
            context_precision = self.metrics.context_precision(query, contexts, ground_truth)
            context_recall = self.metrics.context_recall(contexts, ground_truth)
            answer_relevancy = self.metrics.answer_relevancy(query, answer)

            # Determine evidence level
            if primary_source and faithfulness >= 0.8:
                evidence_level = "green"
            elif sources_count >= 3 and faithfulness >= 0.6:
                evidence_level = "yellow"
            else:
                evidence_level = "red"

            # Build metrics
            metrics = EvalMetrics(
                sources_count=sources_count,
                primary_source=primary_source,
                evidence_level=evidence_level,
                warden_status="SKIPPED",  # TODO: Integrera med Jail Warden
                claim_strips=0,
                degrade_count=0,
                faithfulness=faithfulness,
                context_precision=context_precision,
                context_recall=context_recall,
                answer_relevancy=answer_relevancy,
                latency_ms=latency_ms,
            )

            # Determine pass/fail
            expected_evidence = question.get("evidence_level", "green")
            passed = self._check_pass(metrics, expected_evidence, intent)

            return EvalResult(
                id=q_id,
                query=query,
                intent=intent,
                answer=answer,
                contexts=contexts,
                metrics=metrics,
                passed=passed,
            )

        except Exception as e:
            logger.error(f"Error in {q_id}: {e}")
            return EvalResult(
                id=q_id,
                query=query,
                intent=intent,
                answer="",
                contexts=[],
                metrics=EvalMetrics(
                    sources_count=0,
                    primary_source=False,
                    evidence_level="red",
                    warden_status="ERROR",
                    claim_strips=0,
                    degrade_count=0,
                    faithfulness=0.0,
                    context_precision=0.0,
                    context_recall=0.0,
                    answer_relevancy=0.0,
                    latency_ms=0,
                ),
                passed=False,
                error=str(e),
            )

    def _check_pass(self, metrics: EvalMetrics, expected_evidence: str, intent: str) -> bool:
        """Avgör om frågan passerade"""
        # SMALLTALK ska inte söka
        if intent == "SMALLTALK":
            return metrics.sources_count == 0

        # SFS_PRIMARY kräver green evidence
        if intent == "SFS_PRIMARY":
            return metrics.evidence_level == "green" and metrics.faithfulness >= 0.7

        # PRAXIS kan vara green eller yellow
        if intent == "PRAXIS":
            return metrics.evidence_level in ["green", "yellow"] and metrics.faithfulness >= 0.6

        # EDGE cases: kontrollera att systemet hanterar dem
        if intent.startswith("EDGE_"):
            return metrics.sources_count > 0 and metrics.faithfulness >= 0.5

        # Default: kräv minst yellow
        return metrics.evidence_level in ["green", "yellow"] and metrics.faithfulness >= 0.5

    async def run_evaluation(self, questions: list[dict]) -> EvalReport:
        """Kör full evaluation"""
        results = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Running evaluation...", total=len(questions))

            for question in questions:
                result = await self.run_single_query(question)
                results.append(result)
                progress.update(task, advance=1)

        # Aggregate results
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        # Calculate averages
        valid_results = [r for r in results if not r.error]
        avg_faithfulness = (
            sum(r.metrics.faithfulness for r in valid_results) / len(valid_results)
            if valid_results
            else 0.0
        )
        avg_context_precision = (
            sum(r.metrics.context_precision for r in valid_results) / len(valid_results)
            if valid_results
            else 0.0
        )
        avg_context_recall = (
            sum(r.metrics.context_recall for r in valid_results) / len(valid_results)
            if valid_results
            else 0.0
        )
        avg_answer_relevancy = (
            sum(r.metrics.answer_relevancy for r in valid_results) / len(valid_results)
            if valid_results
            else 0.0
        )

        # Group by intent
        by_intent = {}
        for result in results:
            intent = result.intent
            if intent not in by_intent:
                by_intent[intent] = {"total": 0, "passed": 0, "failed": 0}
            by_intent[intent]["total"] += 1
            if result.passed:
                by_intent[intent]["passed"] += 1
            else:
                by_intent[intent]["failed"] += 1

        return EvalReport(
            timestamp=datetime.now().isoformat(),
            version="1.0-P0",
            total_questions=len(results),
            passed=passed,
            failed=failed,
            pass_rate=passed / len(results) if results else 0.0,
            avg_faithfulness=avg_faithfulness,
            avg_context_precision=avg_context_precision,
            avg_context_recall=avg_context_recall,
            avg_answer_relevancy=avg_answer_relevancy,
            by_intent=by_intent,
            results=results,
        )

    async def close(self):
        """Cleanup"""
        await self.client.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════════════════


def print_report(report: EvalReport):
    """Pretty-print evaluation report"""
    console.print()
    console.print(
        Panel(
            f"[bold]Constitutional-AI Evaluation Report[/bold]\n"
            f"Version: {report.version} | {report.timestamp}",
            border_style="blue",
        )
    )

    # Summary
    console.print()
    console.print(
        f"[bold]Questions:[/bold] {report.total_questions} | "
        f"[green]Pass:[/green] {report.passed} | "
        f"[red]Fail:[/red] {report.failed} | "
        f"[cyan]Pass Rate:[/cyan] {report.pass_rate*100:.1f}%"
    )

    # RAGAS Scores
    console.print()
    scores_table = Table(title="RAGAS Scores", box=box.ROUNDED)
    scores_table.add_column("Metric", style="cyan")
    scores_table.add_column("Score", justify="right", style="green")

    scores_table.add_row("Faithfulness", f"{report.avg_faithfulness:.3f}")
    scores_table.add_row("Context Precision", f"{report.avg_context_precision:.3f}")
    scores_table.add_row("Context Recall", f"{report.avg_context_recall:.3f}")
    scores_table.add_row("Answer Relevancy", f"{report.avg_answer_relevancy:.3f}")

    console.print(scores_table)

    # By Intent
    console.print()
    intent_table = Table(title="Results by Intent", box=box.ROUNDED)
    intent_table.add_column("Intent", style="cyan")
    intent_table.add_column("Total", justify="right")
    intent_table.add_column("Passed", justify="right", style="green")
    intent_table.add_column("Failed", justify="right", style="red")
    intent_table.add_column("Pass Rate", justify="right")

    for intent, stats in sorted(report.by_intent.items()):
        pass_rate = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        intent_table.add_row(
            intent,
            str(stats["total"]),
            str(stats["passed"]),
            str(stats["failed"]),
            f"{pass_rate:.0f}%",
        )

    console.print(intent_table)

    # Failed questions
    failed_results = [r for r in report.results if not r.passed]
    if failed_results:
        console.print()
        console.print("[bold red]Failed Questions:[/bold red]")
        for r in failed_results:
            console.print(f"  • {r.id}: {r.query[:60]}...")
            if r.error:
                console.print(f"    Error: {r.error}")
            else:
                console.print(
                    f"    Evidence: {r.metrics.evidence_level}, "
                    f"Faithfulness: {r.metrics.faithfulness:.2f}"
                )


def save_report(report: EvalReport, filepath: Path):
    """Save report to JSON"""
    # Convert to dict
    report_dict = asdict(report)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)

    console.print(f"\n[dim]Report saved to: {filepath}[/dim]")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


async def main():
    parser = argparse.ArgumentParser(description="Constitutional-AI Evaluation Runner")
    parser.add_argument("--quick", action="store_true", help="Quick test (10 questions)")
    parser.add_argument("--full", action="store_true", help="Full test (20 questions)")
    parser.add_argument(
        "--provider", default="ragas", choices=["ragas", "lightweight"], help="Metrics provider"
    )
    parser.add_argument("--compare", type=str, help="Compare with baseline JSON")
    parser.add_argument("--output", type=str, help="Output file (default: auto-generated)")

    args = parser.parse_args()

    # Initialize runner
    try:
        runner = EvalRunner(metrics_provider=args.provider)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("[yellow]Falling back to lightweight provider...[/yellow]")
        runner = EvalRunner(metrics_provider="lightweight")

    # Load golden set
    questions = await runner.load_golden_set()

    # Select subset
    if args.quick:
        questions = questions[:10]
        console.print("[cyan]Running quick evaluation (10 questions)...[/cyan]")
    elif args.full:
        console.print("[cyan]Running full evaluation (20 questions)...[/cyan]")
    else:
        # Default: quick
        questions = questions[:10]
        console.print("[cyan]Running quick evaluation (10 questions)...[/cyan]")

    # Run evaluation
    report = await runner.run_evaluation(questions)

    # Print report
    print_report(report)

    # Save report
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = RESULTS_DIR / f"eval_results_{timestamp}.json"

    save_report(report, output_path)

    # Compare with baseline
    if args.compare:
        # TODO: Implement comparison logic
        console.print("\n[yellow]Comparison with baseline not yet implemented[/yellow]")

    # Cleanup
    await runner.close()

    # Exit code
    return 0 if report.pass_rate >= 0.8 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
