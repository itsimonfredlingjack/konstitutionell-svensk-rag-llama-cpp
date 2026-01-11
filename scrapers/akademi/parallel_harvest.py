#!/usr/bin/env python3
"""
Parallel Kommun Harvest - Runs 3 orchestrators on different ranges
Worker 1: kommun 1-100
Worker 2: kommun 101-200
Worker 3: kommun 201-286

Each worker uses its own SQLite database to avoid conflicts.
"""

import asyncio
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Worker ranges
WORKERS = [
    {"id": 1, "start": 1, "end": 100, "name": "worker1"},
    {"id": 2, "start": 101, "end": 200, "name": "worker2"},
    {"id": 3, "start": 201, "end": 286, "name": "worker3"},
]


def setup_worker_database(worker: dict, source_db: Path) -> Path:
    """Create a separate database for each worker with their kommun range."""
    worker_db = DATA_DIR / f"harvest_state_{worker['name']}.db"

    # Copy structure and filter data
    source_conn = sqlite3.connect(source_db)
    source_conn.row_factory = sqlite3.Row

    # Remove old worker db if exists
    if worker_db.exists():
        worker_db.unlink()

    worker_conn = sqlite3.connect(worker_db)

    # Copy schema
    source_conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='harvest_tasks'")
    schema = source_conn.fetchone()
    if schema:
        worker_conn.execute(schema[0])

    # Get all kommuner sorted by priority/name
    source_conn.execute("""
        SELECT * FROM harvest_tasks
        ORDER BY priority, namn
    """)
    all_tasks = source_conn.fetchall()

    # Filter to this worker's range (1-indexed)
    start_idx = worker["start"] - 1
    end_idx = worker["end"]
    worker_tasks = all_tasks[start_idx:end_idx]

    # Insert filtered tasks, reset status to pending
    columns = [
        desc[0] for desc in source_conn.execute("SELECT * FROM harvest_tasks LIMIT 1").description
    ]
    placeholders = ", ".join(["?" for _ in columns])

    for task in worker_tasks:
        values = list(task)
        # Reset status to pending for fresh run
        status_idx = columns.index("status")
        values[status_idx] = "pending"
        # Clear timing fields
        for field in ["started_at", "finished_at"]:
            if field in columns:
                values[columns.index(field)] = None

        worker_conn.execute(
            f"INSERT INTO harvest_tasks ({', '.join(columns)}) VALUES ({placeholders})", values
        )

    worker_conn.commit()

    # Create harvest_runs table if it exists in source
    source_conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='harvest_runs'")
    runs_schema = source_conn.fetchone()
    if runs_schema:
        worker_conn.execute(runs_schema[0])
        worker_conn.commit()

    source_conn.close()
    worker_conn.close()

    print(
        f"Worker {worker['id']}: Created DB with {len(worker_tasks)} kommuner ({worker['start']}-{worker['end']})"
    )
    return worker_db


def create_worker_orchestrator(worker: dict) -> Path:
    """Create a modified orchestrator script for this worker."""
    worker_script = DATA_DIR / f"orchestrator_{worker['name']}.py"

    # Read the original orchestrator
    original = BASE_DIR / "orchestrate_kommuner.py"
    content = original.read_text()

    # Modify the STATE_DB path
    content = content.replace(
        'STATE_DB = BASE_DIR / "data" / "harvest_state.db"',
        f'STATE_DB = BASE_DIR / "data" / "harvest_state_{worker["name"]}.db"',
    )

    # Modify PDF cache to use worker-specific subdir
    content = content.replace(
        'PDF_CACHE = BASE_DIR / "pdf_cache" / "kommun"',
        f'PDF_CACHE = BASE_DIR / "pdf_cache" / "kommun_{worker["name"]}"',
    )

    worker_script.write_text(content)
    worker_script.chmod(0o755)

    return worker_script


async def run_worker(worker: dict, source_db: Path):
    """Run a single worker orchestrator."""
    print(f"\n{'=' * 50}")
    print(f"Starting Worker {worker['id']}: Kommuner {worker['start']}-{worker['end']}")
    print(f"{'=' * 50}\n")

    # Setup database
    worker_db = setup_worker_database(worker, source_db)

    # Create orchestrator script
    worker_script = create_worker_orchestrator(worker)

    # Create PDF cache dir
    cache_dir = BASE_DIR / "pdf_cache" / f"kommun_{worker['name']}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Log file
    log_file = LOGS_DIR / f"harvest_{worker['name']}.log"

    # Run orchestrator
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(worker_script),
        "--workers",
        "3",  # Each parallel worker uses 3 internal workers
        "--delay",
        "8",
        stdout=open(log_file, "w"),
        stderr=asyncio.subprocess.STDOUT,
    )

    print(f"Worker {worker['id']} started (PID: {process.pid}), log: {log_file}")

    return process


async def monitor_progress():
    """Monitor progress across all workers."""
    while True:
        await asyncio.sleep(60)  # Check every minute

        total_done = 0
        total_pending = 0
        total_running = 0

        for worker in WORKERS:
            db_path = DATA_DIR / f"harvest_state_{worker['name']}.db"
            if db_path.exists():
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("SELECT status, COUNT(*) FROM harvest_tasks GROUP BY status")
                stats = dict(cur.fetchall())
                conn.close()

                done = stats.get("done", 0)
                pending = stats.get("pending", 0)
                running = stats.get("running", 0)

                total_done += done
                total_pending += pending
                total_running += running

                total = done + pending + running
                pct = 100 * done / total if total > 0 else 0
                print(f"  Worker {worker['id']}: {done}/{total} ({pct:.0f}%)")

        total = total_done + total_pending + total_running
        pct = 100 * total_done / total if total > 0 else 0
        print(f"\n📊 TOTAL: {total_done}/{total} ({pct:.0f}%) | Running: {total_running}")
        print("-" * 40)

        if total_pending == 0 and total_running == 0:
            print("\n🎉 ALL WORKERS COMPLETE!")
            break


async def main():
    """Main entry point."""
    LOGS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    source_db = DATA_DIR / "harvest_state.db"
    if not source_db.exists():
        print("ERROR: Source database not found at", source_db)
        return

    print("=" * 60)
    print("PARALLEL KOMMUN HARVEST")
    print("=" * 60)
    print(f"Starting {len(WORKERS)} parallel workers...")
    print(f"Source DB: {source_db}")

    # Start all workers
    processes = []
    for worker in WORKERS:
        proc = await run_worker(worker, source_db)
        processes.append(proc)
        await asyncio.sleep(2)  # Stagger starts

    print("\n" + "=" * 60)
    print("All workers started! Monitoring progress...")
    print("=" * 60)

    # Run monitor and wait for all processes
    monitor_task = asyncio.create_task(monitor_progress())

    try:
        # Wait for all processes
        await asyncio.gather(*[p.wait() for p in processes])
    except KeyboardInterrupt:
        print("\nShutting down workers...")
        for p in processes:
            p.terminate()

    monitor_task.cancel()

    # Final summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    for worker in WORKERS:
        db_path = DATA_DIR / f"harvest_state_{worker['name']}.db"
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT SUM(pdfs_found), SUM(pdfs_downloaded), SUM(bytes_total) FROM harvest_tasks WHERE status='done'"
            )
            row = cur.fetchone()
            conn.close()

            pdfs = row[0] or 0
            downloaded = row[1] or 0
            size_gb = (row[2] or 0) / 1024 / 1024 / 1024
            print(
                f"Worker {worker['id']}: {pdfs:,} PDFs found, {downloaded:,} downloaded ({size_gb:.1f} GB)"
            )


if __name__ == "__main__":
    asyncio.run(main())
