#!/usr/bin/env python3
"""
Chunk Quality Analysis for ChromaDB Collections
===============================================

Analyzes chunk quality in ChromaDB to identify issues that may degrade retrieval precision.
Samples chunks from all collections and evaluates:
- Length distribution (too short, too long, optimal)
- Metadata completeness per collection type
- Boundary quality (mid-sentence starts, orphaned references)
- SFS structural integrity

Usage:
    python eval/chunk_quality_analysis.py                    # Default 100 samples/collection
    python eval/chunk_quality_analysis.py --sample-size 200  # Custom sample size

Output:
    - Console report with Rich formatting
    - Markdown report: eval/chunk_quality_report.md
"""

import argparse
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import chromadb
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

# Setup
console = Console()

# Paths
BASE_DIR = Path(__file__).parent.parent
EVAL_DIR = Path(__file__).parent
CHROMADB_PATH = BASE_DIR / "chromadb_data"
REPORT_PATH = EVAL_DIR / "chunk_quality_report.md"

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Collections to analyze (BGE-M3 1024-dim collections)
COLLECTIONS = [
    "sfs_lagtext_bge_m3_1024",
    "riksdag_documents_p1_bge_m3_1024",
    "swedish_gov_docs_bge_m3_1024",
    "diva_research_bge_m3_1024",
    "procedural_guides_bge_m3_1024",
]

# Length thresholds (in characters)
MIN_CHUNK_LENGTH = 200  # Too short to be useful
MAX_CHUNK_LENGTH = 4000  # Too long, may dilute relevance
OPTIMAL_MIN = 500
OPTIMAL_MAX = 3500

# Required metadata fields by collection type
METADATA_REQUIREMENTS = {
    "sfs_lagtext_bge_m3_1024": {
        "required": ["sfs_nummer", "titel"],
        "optional": ["kapitel", "paragraf", "rubrik"],
    },
    "riksdag_documents_p1_bge_m3_1024": {
        "required": ["titel", "beteckning"],
        "optional": ["dok_typ", "dok_datum", "organ"],
    },
    "swedish_gov_docs_bge_m3_1024": {
        "required": ["title"],
        "optional": ["source", "date", "document_type"],
    },
    "diva_research_bge_m3_1024": {
        "required": ["title"],
        "optional": ["abstract", "year", "author", "keywords"],
    },
    "procedural_guides_bge_m3_1024": {
        "required": ["title"],
        "optional": ["source", "category"],
    },
}

# Boundary issue detection patterns (Swedish)
CONTINUATION_PATTERNS = [
    (r"^\s*[a-zåäö]", "starts_lowercase"),  # Mid-sentence start
    (r"^\s*(samt|eller|och|men|dock|därtill)\s", "starts_conjunction"),  # Starts with conjunction
    (r"^\s*(enligt|såsom|exempelvis)\s", "starts_reference"),  # Starts with reference word
    (r"^\s*(den|det|de|denna|detta|dessa)\s", "starts_pronoun"),  # Dangling demonstrative
]

ORPHANED_REFERENCE_PATTERNS = [
    (r"(se|enligt|jfr)\s+(ovan|nedan)", "reference_outside"),  # References to outside chunk
    (r"(detta|nämnda|föregående)\s+(stycke|kapitel|paragraf)", "dangling_reference"),
    (r"(som (ovan|nedan) (nämnts|angivits|beskrivits))", "narrative_reference"),
]

# SFS structure patterns for integrity check
SFS_STRUCTURE_PATTERNS = [
    (r"§\s*\d+", "paragraph_marker"),
    (r"\d+\s*§", "paragraph_marker_alt"),
    (r"\d+\s+kap\.", "chapter_marker"),
    (r"Kapitel\s+\d+", "chapter_full"),
    (r"Artikel\s+\d+", "article_marker"),
]


# ═══════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ChunkIssue:
    """A specific issue found in a chunk."""

    chunk_id: str
    issue_type: str  # "too_short", "too_long", "missing_metadata", "boundary", etc.
    description: str
    severity: str  # "low", "medium", "high"
    snippet: str = ""  # First 100 chars of chunk for context


@dataclass
class CollectionStats:
    """Statistics for a single collection."""

    name: str
    total_count: int
    sampled_count: int

    # Length stats
    lengths: list[int] = field(default_factory=list)
    too_short_count: int = 0
    too_long_count: int = 0
    optimal_count: int = 0

    # Metadata stats
    metadata_complete_count: int = 0
    missing_required: dict[str, int] = field(default_factory=dict)
    missing_optional: dict[str, int] = field(default_factory=dict)

    # Boundary quality
    boundary_issues_count: int = 0
    continuation_issues: int = 0
    orphaned_reference_issues: int = 0

    # SFS specific (if applicable)
    sfs_chunks_with_structure: int = 0

    # Issues list
    issues: list[ChunkIssue] = field(default_factory=list)

    @property
    def avg_length(self) -> float:
        return statistics.mean(self.lengths) if self.lengths else 0

    @property
    def median_length(self) -> float:
        return statistics.median(self.lengths) if self.lengths else 0

    @property
    def length_stddev(self) -> float:
        return statistics.stdev(self.lengths) if len(self.lengths) > 1 else 0

    @property
    def metadata_completeness(self) -> float:
        return self.metadata_complete_count / self.sampled_count if self.sampled_count > 0 else 0

    @property
    def boundary_quality(self) -> float:
        return (
            1 - (self.boundary_issues_count / self.sampled_count) if self.sampled_count > 0 else 0
        )


@dataclass
class AnalysisReport:
    """Complete analysis report."""

    timestamp: str
    total_chunks_sampled: int = 0
    collections: dict[str, CollectionStats] = field(default_factory=dict)

    @property
    def avg_length(self) -> float:
        all_lengths = []
        for stats in self.collections.values():
            all_lengths.extend(stats.lengths)
        return statistics.mean(all_lengths) if all_lengths else 0

    @property
    def overall_metadata_completeness(self) -> float:
        total = sum(s.sampled_count for s in self.collections.values())
        complete = sum(s.metadata_complete_count for s in self.collections.values())
        return complete / total if total > 0 else 0

    @property
    def overall_boundary_quality(self) -> float:
        total = sum(s.sampled_count for s in self.collections.values())
        issues = sum(s.boundary_issues_count for s in self.collections.values())
        return 1 - (issues / total) if total > 0 else 0

    @property
    def all_issues(self) -> list[ChunkIssue]:
        issues = []
        for stats in self.collections.values():
            issues.extend(stats.issues)
        return issues


# ═══════════════════════════════════════════════════════════════════════════
# ANALYZER
# ═══════════════════════════════════════════════════════════════════════════


class ChunkQualityAnalyzer:
    """Analyzes chunk quality across ChromaDB collections."""

    def __init__(self, chromadb_path: Path, sample_size: int = 100):
        self.chromadb_path = chromadb_path
        self.sample_size = sample_size
        self.client: chromadb.PersistentClient | None = None

    def connect(self) -> None:
        """Connect to ChromaDB (read-only)."""
        if not self.chromadb_path.exists():
            raise FileNotFoundError(f"ChromaDB not found at {self.chromadb_path}")

        console.print(f"[cyan]Connecting to ChromaDB at {self.chromadb_path}[/cyan]")
        self.client = chromadb.PersistentClient(path=str(self.chromadb_path))

        # List available collections
        available = [c.name for c in self.client.list_collections()]
        console.print(f"[dim]Available collections: {len(available)}[/dim]")

    def _sample_collection(
        self, collection_name: str
    ) -> tuple[list[str], list[str], list[dict], int]:
        """
        Sample chunks from a collection using systematic sampling.

        Returns:
            (ids, documents, metadatas, total_count)
        """
        try:
            collection = self.client.get_collection(collection_name)
            total = collection.count()

            if total == 0:
                return [], [], [], 0

            # Systematic sampling: evenly spaced offsets
            if total <= self.sample_size:
                # Get all if smaller than sample size
                result = collection.get(include=["documents", "metadatas"])
                return result["ids"], result["documents"], result["metadatas"], total

            # Calculate step size for systematic sampling
            step = total // self.sample_size
            sampled_ids = []
            sampled_docs = []
            sampled_metas = []

            for i in range(self.sample_size):
                offset = i * step
                batch = collection.get(
                    limit=1,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                if batch["ids"]:
                    sampled_ids.append(batch["ids"][0])
                    sampled_docs.append(batch["documents"][0] if batch["documents"] else "")
                    sampled_metas.append(batch["metadatas"][0] if batch["metadatas"] else {})

            return sampled_ids, sampled_docs, sampled_metas, total

        except Exception as e:
            console.print(f"[red]Error sampling {collection_name}: {e}[/red]")
            return [], [], [], 0

    def _analyze_length(self, doc: str, chunk_id: str, stats: CollectionStats) -> None:
        """Analyze chunk length."""
        length = len(doc)
        stats.lengths.append(length)

        if length < MIN_CHUNK_LENGTH:
            stats.too_short_count += 1
            stats.issues.append(
                ChunkIssue(
                    chunk_id=chunk_id,
                    issue_type="too_short",
                    description=f"Chunk only {length} chars (min: {MIN_CHUNK_LENGTH})",
                    severity="medium",
                    snippet=doc[:100],
                )
            )
        elif length > MAX_CHUNK_LENGTH:
            stats.too_long_count += 1
            stats.issues.append(
                ChunkIssue(
                    chunk_id=chunk_id,
                    issue_type="too_long",
                    description=f"Chunk has {length} chars (max: {MAX_CHUNK_LENGTH})",
                    severity="low",
                    snippet=doc[:100],
                )
            )
        elif OPTIMAL_MIN <= length <= OPTIMAL_MAX:
            stats.optimal_count += 1

    def _analyze_metadata(
        self, metadata: dict, chunk_id: str, collection_name: str, stats: CollectionStats
    ) -> None:
        """Analyze metadata completeness."""
        requirements = METADATA_REQUIREMENTS.get(
            collection_name, {"required": ["title"], "optional": []}
        )

        missing_required = []
        missing_optional = []

        for field_name in requirements["required"]:
            if not metadata.get(field_name):
                missing_required.append(field_name)
                stats.missing_required[field_name] = stats.missing_required.get(field_name, 0) + 1

        for field_name in requirements["optional"]:
            if not metadata.get(field_name):
                missing_optional.append(field_name)
                stats.missing_optional[field_name] = stats.missing_optional.get(field_name, 0) + 1

        if not missing_required:
            stats.metadata_complete_count += 1
        else:
            stats.issues.append(
                ChunkIssue(
                    chunk_id=chunk_id,
                    issue_type="missing_metadata",
                    description=f"Missing required: {', '.join(missing_required)}",
                    severity="high",
                    snippet="",
                )
            )

    def _analyze_boundary(self, doc: str, chunk_id: str, stats: CollectionStats) -> None:
        """Analyze chunk boundary quality."""
        has_issue = False

        # Check continuation patterns (bad starts)
        for pattern, issue_name in CONTINUATION_PATTERNS:
            if re.match(pattern, doc, re.IGNORECASE):
                stats.continuation_issues += 1
                has_issue = True
                stats.issues.append(
                    ChunkIssue(
                        chunk_id=chunk_id,
                        issue_type=f"boundary_{issue_name}",
                        description=f"Chunk starts mid-context ({issue_name})",
                        severity="medium",
                        snippet=doc[:100],
                    )
                )
                break  # Only count once per chunk

        # Check orphaned references
        for pattern, issue_name in ORPHANED_REFERENCE_PATTERNS:
            if re.search(pattern, doc, re.IGNORECASE):
                stats.orphaned_reference_issues += 1
                has_issue = True
                stats.issues.append(
                    ChunkIssue(
                        chunk_id=chunk_id,
                        issue_type=f"reference_{issue_name}",
                        description=f"Contains orphaned reference ({issue_name})",
                        severity="low",
                        snippet=doc[:100],
                    )
                )
                break  # Only count once per chunk

        if has_issue:
            stats.boundary_issues_count += 1

    def _analyze_sfs_structure(self, doc: str, stats: CollectionStats) -> None:
        """Check if SFS chunks preserve structural markers."""
        for pattern, _ in SFS_STRUCTURE_PATTERNS:
            if re.search(pattern, doc):
                stats.sfs_chunks_with_structure += 1
                break

    def analyze_collection(self, collection_name: str) -> CollectionStats:
        """Analyze a single collection."""
        ids, docs, metas, total = self._sample_collection(collection_name)

        stats = CollectionStats(
            name=collection_name,
            total_count=total,
            sampled_count=len(ids),
        )

        if not ids:
            return stats

        is_sfs = "sfs" in collection_name.lower()

        for chunk_id, doc, meta in zip(ids, docs, metas):
            if not doc:
                continue

            # Length analysis
            self._analyze_length(doc, chunk_id, stats)

            # Metadata analysis
            self._analyze_metadata(meta or {}, chunk_id, collection_name, stats)

            # Boundary analysis
            self._analyze_boundary(doc, chunk_id, stats)

            # SFS structure check
            if is_sfs:
                self._analyze_sfs_structure(doc, stats)

        return stats

    def run_analysis(self) -> AnalysisReport:
        """Run full analysis across all collections."""
        self.connect()

        report = AnalysisReport(timestamp=datetime.now().isoformat())

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Analyzing collections...", total=len(COLLECTIONS))

            for collection_name in COLLECTIONS:
                progress.update(task, description=f"[cyan]Analyzing {collection_name}...")

                # Check if collection exists
                available = [c.name for c in self.client.list_collections()]
                if collection_name not in available:
                    console.print(f"[yellow]Skipping {collection_name} (not found)[/yellow]")
                    progress.update(task, advance=1)
                    continue

                stats = self.analyze_collection(collection_name)
                report.collections[collection_name] = stats
                report.total_chunks_sampled += stats.sampled_count

                progress.update(task, advance=1)

        return report


# ═══════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════


def print_console_report(report: AnalysisReport) -> None:
    """Print report to console using Rich."""
    console.print()
    console.print(
        Panel(
            f"[bold]Chunk Quality Analysis Report[/bold]\nGenerated: {report.timestamp}",
            border_style="blue",
        )
    )

    # Summary table
    console.print()
    summary_table = Table(title="Summary", box=box.ROUNDED)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", justify="right")

    summary_table.add_row("Total Chunks Sampled", f"{report.total_chunks_sampled:,}")
    summary_table.add_row("Average Length", f"{report.avg_length:,.0f} chars")
    summary_table.add_row(
        "Metadata Completeness",
        f"[{'green' if report.overall_metadata_completeness >= 0.9 else 'yellow'}]"
        f"{report.overall_metadata_completeness:.1%}[/]",
    )
    summary_table.add_row(
        "Boundary Quality",
        f"[{'green' if report.overall_boundary_quality >= 0.8 else 'yellow'}]"
        f"{report.overall_boundary_quality:.1%}[/]",
    )

    console.print(summary_table)

    # Per-collection stats
    console.print()
    coll_table = Table(title="Per-Collection Statistics", box=box.ROUNDED)
    coll_table.add_column("Collection", style="cyan", max_width=35)
    coll_table.add_column("Total", justify="right")
    coll_table.add_column("Sampled", justify="right")
    coll_table.add_column("Avg Len", justify="right")
    coll_table.add_column("Short%", justify="right")
    coll_table.add_column("Meta%", justify="right")
    coll_table.add_column("Bound%", justify="right")

    for name, stats in report.collections.items():
        short_pct = stats.too_short_count / stats.sampled_count if stats.sampled_count > 0 else 0
        short_style = "red" if short_pct > 0.1 else "green"
        meta_style = "green" if stats.metadata_completeness >= 0.9 else "yellow"
        bound_style = "green" if stats.boundary_quality >= 0.8 else "yellow"

        # Shorten collection name for display
        short_name = name.replace("_bge_m3_1024", "")

        coll_table.add_row(
            short_name,
            f"{stats.total_count:,}",
            f"{stats.sampled_count}",
            f"{stats.avg_length:,.0f}",
            f"[{short_style}]{short_pct:.0%}[/]",
            f"[{meta_style}]{stats.metadata_completeness:.0%}[/]",
            f"[{bound_style}]{stats.boundary_quality:.0%}[/]",
        )

    console.print(coll_table)

    # Issue summary
    all_issues = report.all_issues
    if all_issues:
        console.print()
        console.print(f"[bold red]Issues Found: {len(all_issues)}[/bold red]")

        # Group by type
        issue_types = {}
        for issue in all_issues:
            issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1

        for issue_type, count in sorted(issue_types.items(), key=lambda x: -x[1])[:10]:
            console.print(f"  • {issue_type}: {count}")


def generate_markdown_report(report: AnalysisReport) -> Path:
    """Generate Markdown report file."""
    lines = [
        "# Chunk Quality Analysis Report",
        "",
        f"**Generated:** {report.timestamp}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Chunks Sampled | {report.total_chunks_sampled:,} |",
        f"| Average Length | {report.avg_length:,.0f} chars |",
        f"| Metadata Completeness | {report.overall_metadata_completeness:.1%} |",
        f"| Boundary Quality | {report.overall_boundary_quality:.1%} |",
        "",
        "---",
        "",
        "## Per-Collection Statistics",
        "",
        "| Collection | Total Docs | Sampled | Avg Length | Too Short | Too Long | Metadata % | Boundary % |",
        "|------------|------------|---------|------------|-----------|----------|------------|------------|",
    ]

    for name, stats in report.collections.items():
        short_pct = (
            stats.too_short_count / stats.sampled_count * 100 if stats.sampled_count > 0 else 0
        )
        long_pct = (
            stats.too_long_count / stats.sampled_count * 100 if stats.sampled_count > 0 else 0
        )
        short_name = name.replace("_bge_m3_1024", "")

        lines.append(
            f"| {short_name} | {stats.total_count:,} | {stats.sampled_count} | "
            f"{stats.avg_length:,.0f} | {short_pct:.1f}% | {long_pct:.1f}% | "
            f"{stats.metadata_completeness:.1%} | {stats.boundary_quality:.1%} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Length Distribution",
            "",
        ]
    )

    for name, stats in report.collections.items():
        short_name = name.replace("_bge_m3_1024", "")
        lines.extend(
            [
                f"### {short_name}",
                "",
                f"- **Min:** {min(stats.lengths):,} chars" if stats.lengths else "- No data",
                f"- **Max:** {max(stats.lengths):,} chars" if stats.lengths else "",
                f"- **Mean:** {stats.avg_length:,.0f} chars",
                f"- **Median:** {stats.median_length:,.0f} chars",
                f"- **Std Dev:** {stats.length_stddev:,.0f} chars",
                "",
            ]
        )

    # Missing metadata breakdown
    lines.extend(
        [
            "---",
            "",
            "## Metadata Analysis",
            "",
        ]
    )

    for name, stats in report.collections.items():
        if stats.missing_required or stats.missing_optional:
            short_name = name.replace("_bge_m3_1024", "")
            lines.append(f"### {short_name}")
            lines.append("")

            if stats.missing_required:
                lines.append("**Missing Required Fields:**")
                for field_name, count in sorted(
                    stats.missing_required.items(), key=lambda x: -x[1]
                ):
                    pct = count / stats.sampled_count * 100
                    lines.append(f"- `{field_name}`: {count} ({pct:.1f}%)")
                lines.append("")

            if stats.missing_optional:
                lines.append("**Missing Optional Fields:**")
                for field_name, count in sorted(
                    stats.missing_optional.items(), key=lambda x: -x[1]
                )[:5]:
                    pct = count / stats.sampled_count * 100
                    lines.append(f"- `{field_name}`: {count} ({pct:.1f}%)")
                lines.append("")

    # Boundary issues
    lines.extend(
        [
            "---",
            "",
            "## Boundary Quality Issues",
            "",
        ]
    )

    all_issues = report.all_issues
    boundary_issues = [
        i for i in all_issues if i.issue_type.startswith(("boundary_", "reference_"))
    ]

    if boundary_issues:
        # Group by type
        issue_types = {}
        for issue in boundary_issues:
            issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1

        lines.append("| Issue Type | Count |")
        lines.append("|------------|-------|")
        for issue_type, count in sorted(issue_types.items(), key=lambda x: -x[1]):
            lines.append(f"| {issue_type} | {count} |")

        lines.append("")
        lines.append("### Example Problem Chunks")
        lines.append("")

        # Show up to 5 examples
        for issue in boundary_issues[:5]:
            lines.append(f"**Chunk ID:** `{issue.chunk_id}`")
            lines.append(f"- **Issue:** {issue.description}")
            if issue.snippet:
                lines.append(f"- **Snippet:** `{issue.snippet[:80]}...`")
            lines.append("")
    else:
        lines.append("No significant boundary issues detected.")
        lines.append("")

    # SFS-specific analysis
    sfs_collections = [
        (name, stats)
        for name, stats in report.collections.items()
        if "sfs" in name.lower() and stats.sampled_count > 0
    ]

    if sfs_collections:
        lines.extend(
            [
                "---",
                "",
                "## SFS Structural Integrity",
                "",
            ]
        )

        for name, stats in sfs_collections:
            short_name = name.replace("_bge_m3_1024", "")
            structure_pct = (
                stats.sfs_chunks_with_structure / stats.sampled_count
                if stats.sampled_count > 0
                else 0
            )
            lines.append(
                f"- **{short_name}:** {stats.sfs_chunks_with_structure}/{stats.sampled_count} "
                f"({structure_pct:.1%}) chunks contain § or chapter markers"
            )
        lines.append("")

    # Recommendations
    lines.extend(
        [
            "---",
            "",
            "## Recommendations",
            "",
        ]
    )

    recommendations = []

    # Check for too many short chunks
    total_short = sum(s.too_short_count for s in report.collections.values())
    total_sampled = report.total_chunks_sampled
    if total_short / total_sampled > 0.1 if total_sampled > 0 else False:
        recommendations.append(
            f"1. **Reduce short chunks** - {total_short} ({total_short / total_sampled:.1%}) "
            f"chunks are under {MIN_CHUNK_LENGTH} chars. Consider increasing minimum chunk size "
            "or merging small adjacent chunks."
        )

    # Check metadata completeness
    if report.overall_metadata_completeness < 0.9:
        recommendations.append(
            f"2. **Improve metadata extraction** - Only {report.overall_metadata_completeness:.1%} "
            "of chunks have complete required metadata. Verify indexing pipeline preserves all fields."
        )

    # Check boundary quality
    if report.overall_boundary_quality < 0.8:
        recommendations.append(
            f"3. **Adjust chunking boundaries** - {1 - report.overall_boundary_quality:.1%} "
            "of chunks have boundary issues. Consider tuning boundary detection regex patterns."
        )

    # Check for orphaned references
    total_orphaned = sum(s.orphaned_reference_issues for s in report.collections.values())
    if total_orphaned > total_sampled * 0.05:
        recommendations.append(
            f"4. **Handle cross-chunk references** - {total_orphaned} chunks contain orphaned "
            "references ('enligt ovan', 'se nedan'). Consider context window expansion or "
            "reference resolution during retrieval."
        )

    if recommendations:
        lines.extend(recommendations)
    else:
        lines.append("No significant issues requiring immediate action.")

    lines.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return REPORT_PATH


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze chunk quality in ChromaDB")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of chunks to sample per collection (default: 100)",
    )
    parser.add_argument(
        "--chromadb-path",
        type=str,
        default=str(CHROMADB_PATH),
        help=f"Path to ChromaDB (default: {CHROMADB_PATH})",
    )
    args = parser.parse_args()

    console.print("[bold]Chunk Quality Analysis[/bold]")
    console.print(f"Sample size: {args.sample_size} per collection")
    console.print()

    start_time = time.time()

    try:
        analyzer = ChunkQualityAnalyzer(
            chromadb_path=Path(args.chromadb_path),
            sample_size=args.sample_size,
        )
        report = analyzer.run_analysis()

        # Print console report
        print_console_report(report)

        # Generate markdown report
        md_path = generate_markdown_report(report)

        elapsed = time.time() - start_time
        console.print()
        console.print(f"[dim]Markdown report saved: {md_path}[/dim]")
        console.print(f"[dim]Analysis completed in {elapsed:.1f}s[/dim]")

        return 0

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
