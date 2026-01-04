#!/usr/bin/env python3
"""
Embedding Completion Notifier - Uses n8n outbox_publisher for Telegram notifications.

Inserts messages into PostgreSQL outbox_messages table.
The outbox_publisher n8n workflow sends them to Telegram automatically.

Usage:
    nohup python embedding_completion_notifier.py > logs/notifier.log 2>&1 &
"""

import os
import re
import subprocess
import time
from datetime import datetime

import psycopg2

# Configuration
CONFIG = {
    "poll_interval": 300,  # 5 minutes
    "log_file": "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/logs/diva_embed.log",
    "failure_threshold": 0.05,  # 5%
    "postgres": {
        "host": "localhost",
        "port": 5434,
        "database": "secondbrain",
        "user": "secondbrain",
        "password": "secondbrain",
    },
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", "8424208702"),
}

START_TIME = datetime.now()


def get_db_connection():
    """Get PostgreSQL connection."""
    return psycopg2.connect(**CONFIG["postgres"])


def insert_outbox_message(subject: str, body: str, priority: int = 5):
    """Insert message into outbox for Telegram delivery."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO outbox (channel, subject, body, priority, channel_config, status, message_type)
            VALUES ('telegram', %s, %s, %s, %s::jsonb, 'pending', 'notification')
            RETURNING id
        """,
            (subject, body, priority, f'{{"chat_id": "{CONFIG["telegram_chat_id"]}"}}'),
        )

        msg_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        print(f"[INFO] Outbox message inserted: {msg_id}")
        return msg_id
    except Exception as e:
        print(f"[ERROR] Failed to insert outbox message: {e}")
        return None


def parse_log_progress(log_file: str) -> dict:
    """Parse the latest progress from corpus_bridge log."""
    try:
        result = subprocess.run(
            ["tail", "-10", log_file], capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        pattern = r"Processed ([\d,]+) / ([\d,]+) \(success: ([\d,]+), failed: ([\d,]+)\)"

        for line in reversed(lines):
            match = re.search(pattern, line)
            if match:
                current = int(match.group(1).replace(",", ""))
                total = int(match.group(2).replace(",", ""))
                success = int(match.group(3).replace(",", ""))
                failed = int(match.group(4).replace(",", ""))

                return {
                    "current": current,
                    "total": total,
                    "success": success,
                    "failed": failed,
                    "progress": current / total if total > 0 else 0,
                    "failure_rate": failed / current if current > 0 else 0,
                }
        return None
    except Exception as e:
        print(f"[ERROR] Failed to parse log: {e}")
        return None


def get_qdrant_count() -> int:
    """Get total points in Qdrant."""
    try:
        import requests

        response = requests.get("http://localhost:6333/collections/documents", timeout=10)
        if response.ok:
            return response.json().get("result", {}).get("points_count", 0)
    except:
        pass
    return 0


def format_duration(start: datetime) -> str:
    """Format duration as Xh Ym."""
    delta = datetime.now() - start
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    return f"{hours}h {minutes}m"


def check_process_running() -> bool:
    """Check if corpus_bridge.py is still running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "corpus_bridge.py"], capture_output=True, timeout=10
        )
        return result.returncode == 0
    except:
        return False


def main():
    print(f"[INFO] Embedding Notifier started at {datetime.now()}")
    print("[INFO] Using PostgreSQL outbox for Telegram delivery")

    # Send start notification
    insert_outbox_message(
        "🔔 Embedding Monitor Started",
        f"Monitoring corpus_bridge.py\nPoll: {CONFIG['poll_interval']}s\nThreshold: {CONFIG['failure_threshold']*100:.0f}%",
        priority=3,
    )

    last_progress = 0
    stall_count = 0
    notified_failure = False

    while True:
        progress = parse_log_progress(CONFIG["log_file"])

        if progress:
            pct = progress["progress"] * 100
            print(
                f"[INFO] {progress['current']:,}/{progress['total']:,} ({pct:.1f}%) - Failed: {progress['failed']:,}"
            )

            # COMPLETE
            if progress["progress"] >= 0.999:
                duration = format_duration(START_TIME)
                qdrant = get_qdrant_count()
                insert_outbox_message(
                    "🎉 DiVA EMBEDDING COMPLETE!",
                    f"📊 {progress['success']:,} docs\n⏱️ {duration}\n✅ Qdrant: {qdrant:,}\n❌ Failed: {progress['failed']:,}",
                    priority=10,
                )
                print("[INFO] Complete! Exiting.")
                break

            # HIGH FAILURE RATE
            if progress["failure_rate"] > CONFIG["failure_threshold"] and not notified_failure:
                insert_outbox_message(
                    "⚠️ HIGH FAILURE RATE",
                    f"Rate: {progress['failure_rate']*100:.1f}%\nFailed: {progress['failed']:,}/{progress['current']:,}",
                    priority=8,
                )
                notified_failure = True

            # STALL DETECTION
            if progress["current"] == last_progress:
                stall_count += 1
                if stall_count >= 3:
                    insert_outbox_message(
                        "⚠️ Embedding Stalled",
                        f"No progress for {stall_count * 5}min\nAt: {progress['current']:,}/{progress['total']:,}",
                        priority=7,
                    )
                    stall_count = 0
            else:
                stall_count = 0
                last_progress = progress["current"]

        # PROCESS DIED
        if not check_process_running():
            progress = parse_log_progress(CONFIG["log_file"])
            if progress and progress["progress"] < 0.99:
                insert_outbox_message(
                    "❌ Embedding Process Died",
                    f"Stopped at: {progress['current']:,}/{progress['total']:,} ({progress['progress']*100:.1f}%)",
                    priority=10,
                )
            break

        time.sleep(CONFIG["poll_interval"])

    print(f"[INFO] Notifier exiting at {datetime.now()}")


if __name__ == "__main__":
    main()
