#!/usr/bin/env python3
"""
Harvest Stats API - Returns JSON stats for n8n dashboard
Run: python harvest_stats_api.py
Output: JSON with harvest statistics
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "harvest_state.db"


def get_harvest_stats():
    """Get comprehensive harvest statistics."""
    if not DB_PATH.exists():
        return {"error": "Database not found", "status": "offline"}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get counts by status
    cur.execute("SELECT status, COUNT(*) as count FROM harvest_tasks GROUP BY status")
    status_counts = {row["status"]: row["count"] for row in cur.fetchall()}

    total = sum(status_counts.values())
    done = status_counts.get("done", 0)
    pending = status_counts.get("pending", 0)
    running = status_counts.get("running", 0)
    failed = status_counts.get("failed", 0)

    # Get aggregated stats for completed tasks
    cur.execute("""
        SELECT
            SUM(pdfs_found) as total_found,
            SUM(pdfs_downloaded) as total_downloaded,
            SUM(bytes_total) as total_bytes,
            MIN(started_at) as first_start,
            MAX(finished_at) as last_finish
        FROM harvest_tasks
        WHERE status = 'done'
    """)
    row = cur.fetchone()

    pdfs_found = row["total_found"] or 0
    pdfs_downloaded = row["total_downloaded"] or 0
    total_bytes = row["total_bytes"] or 0
    first_start = row["first_start"]
    last_finish = row["last_finish"]

    # Calculate throughput and ETA
    throughput_per_hour = 0
    eta_hours = 0
    eta_timestamp = None

    if first_start and last_finish and done > 0:
        try:
            start_dt = datetime.fromisoformat(first_start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(last_finish.replace("Z", "+00:00"))
            elapsed_hours = (end_dt - start_dt).total_seconds() / 3600

            if elapsed_hours > 0:
                throughput_per_hour = done / elapsed_hours
                remaining = pending + running
                if throughput_per_hour > 0:
                    eta_hours = remaining / throughput_per_hour
                    eta_timestamp = (datetime.now() + timedelta(hours=eta_hours)).isoformat()
        except:
            pass

    # Get recent failures (last 10)
    cur.execute("""
        SELECT namn, error_message, finished_at
        FROM harvest_tasks
        WHERE status = 'failed'
        ORDER BY finished_at DESC
        LIMIT 10
    """)
    recent_failures = [
        {"kommun": row["namn"], "error": row["error_message"], "at": row["finished_at"]}
        for row in cur.fetchall()
    ]

    # Check for consecutive failures (alert condition)
    cur.execute("""
        SELECT status FROM harvest_tasks
        WHERE finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 5
    """)
    recent_statuses = [row["status"] for row in cur.fetchall()]
    consecutive_failures = 0
    for s in recent_statuses:
        if s == "failed":
            consecutive_failures += 1
        else:
            break

    # Get currently running kommuner
    cur.execute("SELECT namn FROM harvest_tasks WHERE status = 'running'")
    running_kommuner = [row["namn"] for row in cur.fetchall()]

    # Get last 5 completed
    cur.execute("""
        SELECT namn, pdfs_found, pdfs_downloaded, finished_at
        FROM harvest_tasks
        WHERE status = 'done'
        ORDER BY finished_at DESC
        LIMIT 5
    """)
    recent_completed = [
        {
            "kommun": row["namn"],
            "pdfs_found": row["pdfs_found"],
            "pdfs_downloaded": row["pdfs_downloaded"],
            "at": row["finished_at"],
        }
        for row in cur.fetchall()
    ]

    conn.close()

    # Build response
    progress_pct = round(100 * done / total, 1) if total > 0 else 0

    return {
        "status": "running" if running > 0 else ("completed" if pending == 0 else "paused"),
        "timestamp": datetime.now().isoformat(),
        "progress": {
            "done": done,
            "running": running,
            "pending": pending,
            "failed": failed,
            "total": total,
            "percent": progress_pct,
        },
        "documents": {
            "pdfs_found": pdfs_found,
            "pdfs_downloaded": pdfs_downloaded,
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / 1024 / 1024, 1),
            "total_gb": round(total_bytes / 1024 / 1024 / 1024, 2),
        },
        "performance": {
            "throughput_per_hour": round(throughput_per_hour, 1),
            "eta_hours": round(eta_hours, 1),
            "eta_timestamp": eta_timestamp,
        },
        "alerts": {
            "consecutive_failures": consecutive_failures,
            "alert_triggered": consecutive_failures >= 3,
        },
        "running_kommuner": running_kommuner,
        "recent_completed": recent_completed,
        "recent_failures": recent_failures[:3],
    }


if __name__ == "__main__":
    stats = get_harvest_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
