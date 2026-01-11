#!/usr/bin/env python3
"""
Kommun Document Harvest Orchestrator
=====================================
Parallel batch processing of 286 Swedish municipalities with:
- 5 concurrent workers (AsyncIO)
- SQLite state tracking (resume-capable)
- Priority ordering (small → large)
- Real-time progress display
- Comprehensive error handling

Usage:
    python orchestrate_kommuner.py              # Start/resume harvest
    python orchestrate_kommuner.py --status     # Show current progress
    python orchestrate_kommuner.py --reset      # Reset all to pending
"""

import asyncio
import json
import logging
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

# Rich for beautiful terminal output
try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: 'rich' not installed. Using basic output.")

# Configuration
BASE_DIR = Path(__file__).parent
STATE_DB = BASE_DIR / "data" / "harvest_state.db"
BATCH_LIST = BASE_DIR / "kommuner_batch_list.json"
ERROR_LOG = BASE_DIR / "harvest_errors.log"
RESULTS_DIR = BASE_DIR / "harvest_results"

# Worker settings
MAX_WORKERS = 5
DELAY_BETWEEN_REQUESTS = 10.0  # seconds per worker
MAX_PAGES_PER_KOMMUN = 80
MAX_DOWNLOADS_PER_KOMMUN = 30
TIMEOUT_PER_KOMMUN = 7200  # 2 hours in seconds
MAX_CONSECUTIVE_TIMEOUTS = 3

# Ensure directories exist
STATE_DB.parent.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(ERROR_LOG), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)


@dataclass
class KommunTask:
    """A kommun scraping task."""

    kod: str
    namn: str
    url: str
    priority: int
    status: str = "pending"  # pending, running, done, failed, skipped
    started_at: str | None = None
    finished_at: str | None = None
    pdfs_found: int = 0
    pdfs_downloaded: int = 0
    bytes_total: int = 0
    pages_visited: int = 0
    error_message: str | None = None


class HarvestState:
    """SQLite-backed state management for harvest progress."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS harvest_tasks (
                    kod TEXT PRIMARY KEY,
                    namn TEXT NOT NULL,
                    url TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    started_at TEXT,
                    finished_at TEXT,
                    pdfs_found INTEGER DEFAULT 0,
                    pdfs_downloaded INTEGER DEFAULT 0,
                    bytes_total INTEGER DEFAULT 0,
                    pages_visited INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS harvest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    total_tasks INTEGER,
                    completed_tasks INTEGER DEFAULT 0,
                    failed_tasks INTEGER DEFAULT 0,
                    total_pdfs INTEGER DEFAULT 0,
                    total_bytes INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON harvest_tasks(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_priority ON harvest_tasks(priority)
            """)

    @contextmanager
    def _connect(self):
        """Thread-safe database connection."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def load_tasks(self, tasks: list[dict]):
        """Load tasks from batch list (idempotent - won't overwrite existing)."""
        with self._connect() as conn:
            for task in tasks:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO harvest_tasks
                    (kod, namn, url, priority)
                    VALUES (?, ?, ?, ?)
                """,
                    (task["id"], task["namn"], task["url"], task["priority"]),
                )

    def get_pending_tasks(self, limit: int = None) -> list[KommunTask]:
        """Get pending tasks ordered by priority (small first = priority 2)."""
        with self._connect() as conn:
            query = """
                SELECT * FROM harvest_tasks
                WHERE status = 'pending'
                ORDER BY priority ASC, namn ASC
            """
            if limit:
                query += f" LIMIT {limit}"
            rows = conn.execute(query).fetchall()
            return [KommunTask(**dict(row)) for row in rows]

    def claim_task(self, kod: str) -> bool:
        """Atomically claim a task for processing."""
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE harvest_tasks
                SET status = 'running', started_at = ?
                WHERE kod = ? AND status = 'pending'
            """,
                (datetime.now().isoformat(), kod),
            )
            return result.rowcount > 0

    def complete_task(
        self, kod: str, pdfs_found: int, pdfs_downloaded: int, bytes_total: int, pages_visited: int
    ):
        """Mark task as completed."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE harvest_tasks
                SET status = 'done',
                    finished_at = ?,
                    pdfs_found = ?,
                    pdfs_downloaded = ?,
                    bytes_total = ?,
                    pages_visited = ?
                WHERE kod = ?
            """,
                (
                    datetime.now().isoformat(),
                    pdfs_found,
                    pdfs_downloaded,
                    bytes_total,
                    pages_visited,
                    kod,
                ),
            )

    def fail_task(self, kod: str, error_message: str):
        """Mark task as failed."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE harvest_tasks
                SET status = 'failed',
                    finished_at = ?,
                    error_message = ?
                WHERE kod = ?
            """,
                (datetime.now().isoformat(), error_message[:500], kod),
            )

    def skip_task(self, kod: str, reason: str):
        """Mark task as skipped."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE harvest_tasks
                SET status = 'skipped',
                    finished_at = ?,
                    error_message = ?
                WHERE kod = ?
            """,
                (datetime.now().isoformat(), reason, kod),
            )

    def get_progress(self) -> dict:
        """Get overall progress statistics."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped,
                    SUM(pdfs_found) as total_pdfs_found,
                    SUM(pdfs_downloaded) as total_pdfs_downloaded,
                    SUM(bytes_total) as total_bytes,
                    SUM(pages_visited) as total_pages
                FROM harvest_tasks
            """).fetchone()
            return dict(row)

    def get_recent_completed(self, limit: int = 10) -> list[dict]:
        """Get recently completed tasks."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT kod, namn, status, pdfs_found, pdfs_downloaded, bytes_total,
                       finished_at, error_message
                FROM harvest_tasks
                WHERE status IN ('done', 'failed', 'skipped')
                ORDER BY finished_at DESC
                LIMIT ?
            """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def reset_all(self):
        """Reset all tasks to pending (for testing)."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE harvest_tasks
                SET status = 'pending',
                    started_at = NULL,
                    finished_at = NULL,
                    pdfs_found = 0,
                    pdfs_downloaded = 0,
                    bytes_total = 0,
                    pages_visited = 0,
                    error_message = NULL
            """)

    def reset_running(self):
        """Reset stuck 'running' tasks to pending (for resume after crash)."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE harvest_tasks
                SET status = 'pending',
                    started_at = NULL
                WHERE status = 'running'
            """)


class KommunWorker:
    """Async worker that processes kommun scraping tasks."""

    def __init__(self, worker_id: int, state: HarvestState, delay: float = 10.0):
        self.worker_id = worker_id
        self.state = state
        self.delay = delay
        self.consecutive_timeouts = 0

    async def process_task(self, task: KommunTask) -> tuple[bool, str]:
        """Process a single kommun task. Returns (success, message)."""

        # Import scraper here to avoid circular imports

        logger.info(f"[Worker {self.worker_id}] Starting: {task.namn} ({task.kod})")

        try:
            # Run scraper in thread pool (Playwright is sync)
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = await asyncio.wait_for(
                    loop.run_in_executor(executor, self._run_scraper, task),
                    timeout=TIMEOUT_PER_KOMMUN,
                )

            # Reset timeout counter on success
            self.consecutive_timeouts = 0

            # Update state
            self.state.complete_task(
                task.kod,
                pdfs_found=result.pdfs_found,
                pdfs_downloaded=result.dokument_hamtade,
                bytes_total=result.storlek_bytes,
                pages_visited=result.pages_visited,
            )

            # Save detailed result
            result_file = RESULTS_DIR / f"{task.kod}_{task.namn.replace(' ', '_')}.json"
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(asdict(result), f, indent=2, ensure_ascii=False)

            msg = (
                f"{task.namn}: {result.pdfs_found} PDFs found, {result.dokument_hamtade} downloaded"
            )
            logger.info(f"[Worker {self.worker_id}] Completed: {msg}")
            return True, msg

        except asyncio.TimeoutError:
            self.consecutive_timeouts += 1
            error_msg = f"Timeout after {TIMEOUT_PER_KOMMUN}s"
            self.state.fail_task(task.kod, error_msg)
            logger.warning(f"[Worker {self.worker_id}] {task.namn}: {error_msg}")
            return False, error_msg

        except Exception as e:
            error_msg = str(e)[:200]
            self.state.fail_task(task.kod, error_msg)
            logger.error(f"[Worker {self.worker_id}] {task.namn} failed: {error_msg}")
            return False, error_msg

    def _run_scraper(self, task: KommunTask):
        """Run the scraper (sync, called from thread pool)."""
        from scrape_kommun_deep import DeepKommunScraper

        with DeepKommunScraper(
            kommun_kod=task.kod,
            namn=task.namn,
            url=task.url,
            delay=self.delay,
            max_pages=MAX_PAGES_PER_KOMMUN,
            max_downloads=MAX_DOWNLOADS_PER_KOMMUN,
        ) as scraper:
            return scraper.run()

    def should_skip_due_to_timeouts(self) -> bool:
        """Check if we should skip remaining tasks due to consecutive timeouts."""
        return self.consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS


class HarvestOrchestrator:
    """Main orchestrator for parallel kommun harvesting."""

    def __init__(self, max_workers: int = 5, delay: float = 10.0):
        self.state = HarvestState(STATE_DB)
        self.console = Console() if RICH_AVAILABLE else None
        self.start_time = None
        self.tasks_completed = 0
        self.last_summary_at = 0
        self.max_workers = max_workers
        self.delay = delay

    def load_batch_list(self):
        """Load kommun batch list into state database."""
        if not BATCH_LIST.exists():
            raise FileNotFoundError(f"Batch list not found: {BATCH_LIST}")

        with open(BATCH_LIST) as f:
            data = json.load(f)

        tasks = data.get("kommuner", [])
        self.state.load_tasks(tasks)

        # Reset any stuck 'running' tasks from previous crash
        self.state.reset_running()

        return len(tasks)

    def print_progress(self):
        """Print current progress to terminal."""
        progress = self.state.get_progress()

        total = progress["total"]
        done = progress["done"]
        failed = progress["failed"]
        skipped = progress["skipped"]
        running = progress["running"]
        pending = progress["pending"]

        completed = done + failed + skipped
        pct = (completed / total * 100) if total > 0 else 0

        total_mb = progress["total_bytes"] / (1024 * 1024)
        total_gb = total_mb / 1024

        if self.console:
            table = Table(title="Harvest Progress", show_header=True)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Total kommuner", str(total))
            table.add_row("Completed", f"{completed} ({pct:.1f}%)")
            table.add_row("  ✓ Success", f"[green]{done}[/green]")
            table.add_row("  ✗ Failed", f"[red]{failed}[/red]")
            table.add_row("  ⊘ Skipped", f"[yellow]{skipped}[/yellow]")
            table.add_row("Running", f"[blue]{running}[/blue]")
            table.add_row("Pending", str(pending))
            table.add_row("─" * 15, "─" * 10)
            table.add_row("PDFs found", f"{progress['total_pdfs_found']:,}")
            table.add_row("PDFs downloaded", f"{progress['total_pdfs_downloaded']:,}")
            table.add_row(
                "Total size", f"{total_gb:.2f} GB" if total_gb >= 1 else f"{total_mb:.1f} MB"
            )
            table.add_row("Pages visited", f"{progress['total_pages']:,}")

            if self.start_time:
                elapsed = datetime.now() - self.start_time
                table.add_row("Elapsed time", str(elapsed).split(".")[0])

                if completed > 0:
                    rate = completed / elapsed.total_seconds() * 3600
                    remaining = pending / rate if rate > 0 else 0
                    table.add_row("Rate", f"{rate:.1f} kommuner/hour")
                    table.add_row("ETA", f"{remaining:.1f} hours")

            self.console.print(table)
        else:
            print(f"\n{'=' * 50}")
            print(f"Progress: {completed}/{total} ({pct:.1f}%)")
            print(f"  Success: {done}, Failed: {failed}, Skipped: {skipped}")
            print(f"  Running: {running}, Pending: {pending}")
            print(
                f"PDFs: {progress['total_pdfs_found']:,} found, {progress['total_pdfs_downloaded']:,} downloaded"
            )
            print(f"Size: {total_gb:.2f} GB")
            print(f"{'=' * 50}\n")

    def print_recent(self, limit: int = 5):
        """Print recently completed tasks."""
        recent = self.state.get_recent_completed(limit)

        if not recent:
            return

        if self.console:
            table = Table(title=f"Last {len(recent)} Completed", show_header=True)
            table.add_column("Kommun", style="cyan")
            table.add_column("Status")
            table.add_column("PDFs", justify="right")
            table.add_column("Size", justify="right")

            for r in recent:
                status_style = {
                    "done": "[green]✓[/green]",
                    "failed": "[red]✗[/red]",
                    "skipped": "[yellow]⊘[/yellow]",
                }.get(r["status"], "?")
                mb = r["bytes_total"] / (1024 * 1024)
                table.add_row(r["namn"], status_style, str(r["pdfs_downloaded"]), f"{mb:.1f} MB")
            self.console.print(table)
        else:
            print("\nRecent completed:")
            for r in recent:
                status = {"done": "✓", "failed": "✗", "skipped": "⊘"}.get(r["status"], "?")
                print(f"  {status} {r['namn']}: {r['pdfs_downloaded']} PDFs")

    async def run_workers(self):
        """Run parallel workers to process all pending tasks."""
        self.start_time = datetime.now()

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_workers)

        # Track active workers
        active_tasks = set()
        workers = [KommunWorker(i, self.state, self.delay) for i in range(self.max_workers)]
        worker_idx = 0

        async def process_with_semaphore(task: KommunTask, worker: KommunWorker):
            async with semaphore:
                if worker.should_skip_due_to_timeouts():
                    self.state.skip_task(task.kod, "Skipped due to consecutive timeouts")
                    return False, "Skipped"

                return await worker.process_task(task)

        # Process tasks
        while True:
            # Get pending tasks
            pending = self.state.get_pending_tasks(limit=self.max_workers * 2)

            if not pending and not active_tasks:
                break  # All done

            # Start new tasks
            for task in pending:
                if len(active_tasks) >= self.max_workers:
                    break

                if not self.state.claim_task(task.kod):
                    continue  # Already claimed

                worker = workers[worker_idx % self.max_workers]
                worker_idx += 1

                coro = process_with_semaphore(task, worker)
                async_task = asyncio.create_task(coro)
                active_tasks.add(async_task)

            # Wait for at least one task to complete
            if active_tasks:
                done, active_tasks = await asyncio.wait(
                    active_tasks, return_when=asyncio.FIRST_COMPLETED
                )

                for completed_task in done:
                    self.tasks_completed += 1

                    # Print summary every 50 tasks
                    if self.tasks_completed % 50 == 0:
                        if self.console:
                            self.console.print(
                                f"\n[bold]Progress Update (Task #{self.tasks_completed})[/bold]"
                            )
                        self.print_progress()
                        self.print_recent()

            # Small delay to prevent tight loop
            await asyncio.sleep(0.1)

    async def run(self):
        """Main entry point."""
        # Load tasks
        total = self.load_batch_list()

        if self.console:
            self.console.print(
                Panel.fit(
                    f"[bold green]Kommun Document Harvest[/bold green]\n"
                    f"Total: {total} kommuner\n"
                    f"Workers: {self.max_workers}\n"
                    f"Delay: {self.delay}s per request",
                    title="Starting",
                )
            )
        else:
            print(f"\n{'=' * 50}")
            print("Kommun Document Harvest")
            print(f"Total: {total} kommuner, Workers: {self.max_workers}")
            print(f"{'=' * 50}\n")

        # Show initial progress
        self.print_progress()

        # Run workers
        try:
            await self.run_workers()
        except KeyboardInterrupt:
            logger.info("Harvest interrupted by user")
            if self.console:
                self.console.print("[yellow]Interrupted! Progress saved.[/yellow]")

        # Final report
        self.print_final_report()

    def print_final_report(self):
        """Print final harvest report."""
        progress = self.state.get_progress()

        total_gb = progress["total_bytes"] / (1024 * 1024 * 1024)
        elapsed = datetime.now() - self.start_time if self.start_time else timedelta(0)

        if self.console:
            self.console.print("\n")
            self.console.print(
                Panel.fit(
                    f"[bold]Final Report[/bold]\n\n"
                    f"Kommuner processed: {progress['done'] + progress['failed']}/{progress['total']}\n"
                    f"  ✓ Success: [green]{progress['done']}[/green]\n"
                    f"  ✗ Failed: [red]{progress['failed']}[/red]\n"
                    f"  ⊘ Skipped: [yellow]{progress['skipped']}[/yellow]\n\n"
                    f"PDFs found: {progress['total_pdfs_found']:,}\n"
                    f"PDFs downloaded: {progress['total_pdfs_downloaded']:,}\n"
                    f"Total size: {total_gb:.2f} GB\n"
                    f"Pages visited: {progress['total_pages']:,}\n\n"
                    f"Elapsed time: {str(elapsed).split('.')[0]}\n"
                    f"Results saved to: {RESULTS_DIR}",
                    title="Harvest Complete",
                    border_style="green",
                )
            )
        else:
            print("\n" + "=" * 50)
            print("FINAL REPORT")
            print("=" * 50)
            print(f"Processed: {progress['done'] + progress['failed']}/{progress['total']}")
            print(
                f"Success: {progress['done']}, Failed: {progress['failed']}, Skipped: {progress['skipped']}"
            )
            print(
                f"PDFs: {progress['total_pdfs_found']:,} found, {progress['total_pdfs_downloaded']:,} downloaded"
            )
            print(f"Size: {total_gb:.2f} GB")
            print(f"Time: {str(elapsed).split('.')[0]}")
            print("=" * 50)

    def show_status(self):
        """Show current harvest status without starting workers."""
        self.load_batch_list()
        self.print_progress()
        self.print_recent(10)

    def reset(self):
        """Reset all tasks to pending."""
        self.state.reset_all()
        if self.console:
            self.console.print("[yellow]All tasks reset to pending[/yellow]")
        else:
            print("All tasks reset to pending")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Kommun Document Harvest Orchestrator")
    parser.add_argument("--status", action="store_true", help="Show current progress")
    parser.add_argument("--reset", action="store_true", help="Reset all tasks to pending")
    parser.add_argument("--workers", type=int, default=5, help="Number of workers (default: 5)")
    parser.add_argument(
        "--delay", type=float, default=10.0, help="Delay between requests (default: 10s)"
    )

    args = parser.parse_args()

    orchestrator = HarvestOrchestrator(max_workers=args.workers, delay=args.delay)

    if args.status:
        orchestrator.show_status()
    elif args.reset:
        orchestrator.reset()
    else:
        asyncio.run(orchestrator.run())


if __name__ == "__main__":
    main()
