#!/usr/bin/env python3
"""
ChromaDB Progress Tracker - Standalone Script

Queries ChromaDB directly to get embedding progress and generates formatted output.
Can be used standalone or as a helper for n8n workflows.

Usage:
    python chromadb_progress.py                    # Show progress
    python chromadb_progress.py --json             # JSON output
    python chromadb_progress.py --slack WEBHOOK    # Send to Slack webhook
"""

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional


class ChromaDBProgress:
    """Query ChromaDB and calculate progress metrics."""

    DB_PATH = Path(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data/chroma.sqlite3"
    )
    RIKSDAG_TARGET = 230000
    TOTAL_GOAL = 500000

    def __init__(self):
        self.total_documents = 0
        self.collection_counts: dict[str, int] = {}
        self.timestamp = datetime.now()
        self.error: Optional[str] = None

    def query_database(self) -> bool:
        """Query ChromaDB SQLite database for document counts."""
        if not self.DB_PATH.exists():
            self.error = f"Database not found: {self.DB_PATH}"
            return False

        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            # Get total count
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            result = cursor.fetchone()
            if result:
                self.total_documents = result[0]

            # Get collection breakdown
            try:
                cursor.execute("""
                    SELECT collection_id, COUNT(*) as count
                    FROM embeddings
                    GROUP BY collection_id
                    ORDER BY count DESC
                """)
                for collection_id, count in cursor.fetchall():
                    if collection_id:  # Skip NULL values
                        self.collection_counts[collection_id] = count
            except sqlite3.OperationalError:
                # If collection_id doesn't exist, try alternative schema
                cursor.execute("PRAGMA table_info(embeddings)")
                columns = [col[1] for col in cursor.fetchall()]
                if "collection" in columns:
                    cursor.execute("""
                        SELECT collection, COUNT(*) as count
                        FROM embeddings
                        GROUP BY collection
                        ORDER BY count DESC
                    """)
                    for collection, count in cursor.fetchall():
                        if collection:
                            self.collection_counts[collection] = count

            conn.close()
            return True

        except sqlite3.Error as e:
            self.error = f"Database query failed: {e}"
            return False
        except Exception as e:
            self.error = f"Unexpected error: {e}"
            return False

    def get_percentage(self) -> int:
        """Calculate progress percentage towards goal."""
        return min(int((self.total_documents / self.TOTAL_GOAL) * 100), 100)

    def get_progress_bar(self, length: int = 20) -> str:
        """Generate ASCII progress bar."""
        percentage = self.get_percentage()
        filled = int(length * percentage / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}] {percentage}% ({self.total_documents:,}/{self.TOTAL_GOAL:,})"

    def get_remaining(self) -> int:
        """Calculate documents remaining to goal."""
        return max(0, self.TOTAL_GOAL - self.total_documents)

    def to_dict(self) -> dict:
        """Return progress data as dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_documents": self.total_documents,
            "percentage": self.get_percentage(),
            "progress_bar": self.get_progress_bar(),
            "remaining": self.get_remaining(),
            "collection_counts": self.collection_counts,
            "error": self.error,
        }

    def to_json(self) -> str:
        """Return progress data as JSON."""
        return json.dumps(self.to_dict(), indent=2)

    def to_text(self) -> str:
        """Return formatted text output."""
        if self.error:
            return f"ERROR: {self.error}"

        lines = [
            "📊 Embedding Progress Update",
            "",
            f"Progress: {self.get_progress_bar()}",
            "",
            "Statistics:",
            f"  • Total Documents: {self.total_documents:,}",
            f"  • Percentage Complete: {self.get_percentage()}%",
            f"  • Remaining to Goal: {self.get_remaining():,}",
            f"  • Riksdag Target: {self.RIKSDAG_TARGET:,}",
        ]

        if self.collection_counts:
            lines.extend(
                [
                    "",
                    "Collections:",
                ]
            )
            for name, count in sorted(
                self.collection_counts.items(), key=lambda x: x[1], reverse=True
            ):
                pct = int((count / self.total_documents) * 100) if self.total_documents > 0 else 0
                lines.append(f"  • {name}: {count:,} ({pct}%)")

        lines.extend(
            [
                "",
                f"Last Updated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            ]
        )

        return "\n".join(lines)

    def to_slack_json(self) -> dict:
        """Return Slack-formatted JSON (for webhooks)."""
        percentage = self.get_percentage()

        # Emoji based on progress
        if percentage >= 80:
            emoji = "🟢"
        elif percentage >= 50:
            emoji = "🟡"
        else:
            emoji = "🔴"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Embedding Progress",
                    "emoji": True,
                },
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"`{self.get_progress_bar()}`"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total Documents*\n{self.total_documents:,}"},
                    {"type": "mrkdwn", "text": f"*Progress*\n{self.get_percentage()}%"},
                    {"type": "mrkdwn", "text": f"*Remaining*\n{self.get_remaining():,}"},
                    {"type": "mrkdwn", "text": "*Growth Rate*\nCalculating..."},
                ],
            },
        ]

        if self.collection_counts:
            collection_text = "\n".join(
                [
                    f"• {name}: {count:,}"
                    for name, count in sorted(
                        self.collection_counts.items(), key=lambda x: x[1], reverse=True
                    )
                ]
            )

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Collections*\n{collection_text}"},
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Updated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ],
            }
        )

        return {"blocks": blocks}

    def send_to_slack(self, webhook_url: str) -> bool:
        """Send progress to Slack via webhook."""
        if self.error:
            return False

        payload = json.dumps(self.to_slack_json()).encode("utf-8")

        try:
            req = urllib.request.Request(
                webhook_url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as response:
                return response.status == 200
        except urllib.error.URLError as e:
            self.error = f"Slack webhook failed: {e}"
            return False


def main():
    parser = argparse.ArgumentParser(
        description="ChromaDB Progress Tracker",
        epilog="Examples:\n"
        "  python chromadb_progress.py              # Show progress\n"
        "  python chromadb_progress.py --json       # JSON output\n"
        "  python chromadb_progress.py --slack WEBHOOK_URL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--slack", metavar="WEBHOOK_URL", help="Send to Slack webhook")
    parser.add_argument("--quiet", action="store_true", help="Quiet mode (only errors)")

    args = parser.parse_args()

    # Query database
    tracker = ChromaDBProgress()
    success = tracker.query_database()

    if not success:
        print(f"ERROR: {tracker.error}", file=sys.stderr)
        sys.exit(1)

    # Output based on flags
    if args.json:
        print(tracker.to_json())
    elif args.slack:
        if tracker.send_to_slack(args.slack):
            if not args.quiet:
                print("✓ Sent to Slack successfully")
        else:
            print(f"ERROR: {tracker.error}", file=sys.stderr)
            sys.exit(1)
    else:
        print(tracker.to_text())

    sys.exit(0)


if __name__ == "__main__":
    main()
