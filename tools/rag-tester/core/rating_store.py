"""SQLite-based storage for RAG answer ratings."""

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Rating:
    """A stored rating for a RAG answer."""

    id: int
    question_id: str
    question_text: str
    answer: str
    rating: int  # 1-5
    comment: Optional[str]
    timestamp: str


class RatingStore:
    """SQLite store for RAG answer ratings."""

    def __init__(self, path: str | Path | None = None):
        if path is None:
            path = Path(__file__).parent.parent / "data" / "ratings.db"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_question_id ON ratings(question_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON ratings(timestamp)
            """)
            conn.commit()

    def save_rating(
        self,
        question_id: str,
        question_text: str,
        answer: str,
        rating: int,
        comment: str | None = None,
    ) -> int:
        """
        Save a rating for a RAG answer.

        Args:
            question_id: ID from question bank (or "manual-XXX" for ad-hoc)
            question_text: The actual question asked
            answer: The RAG system's answer
            rating: Score from 1-5
            comment: Optional free-text comment

        Returns:
            The ID of the saved rating
        """
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        timestamp = datetime.now().isoformat()

        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO ratings (question_id, question_text, answer, rating, comment, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (question_id, question_text, answer, rating, comment, timestamp),
            )
            conn.commit()
            return cursor.lastrowid

    def get_history(self, question_id: str) -> list[Rating]:
        """Get all ratings for a specific question."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM ratings WHERE question_id = ? ORDER BY timestamp DESC
                """,
                (question_id,),
            )
            return [
                Rating(
                    id=row["id"],
                    question_id=row["question_id"],
                    question_text=row["question_text"],
                    answer=row["answer"],
                    rating=row["rating"],
                    comment=row["comment"],
                    timestamp=row["timestamp"],
                )
                for row in cursor.fetchall()
            ]

    def get_recent(self, limit: int = 20) -> list[Rating]:
        """Get the most recent ratings."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM ratings ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            )
            return [
                Rating(
                    id=row["id"],
                    question_id=row["question_id"],
                    question_text=row["question_text"],
                    answer=row["answer"],
                    rating=row["rating"],
                    comment=row["comment"],
                    timestamp=row["timestamp"],
                )
                for row in cursor.fetchall()
            ]

    def get_stats(self) -> dict:
        """Get summary statistics."""
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    AVG(rating) as avg_rating,
                    MIN(rating) as min_rating,
                    MAX(rating) as max_rating
                FROM ratings
                """
            )
            row = cursor.fetchone()
            return {
                "total_ratings": row[0],
                "avg_rating": round(row[1], 2) if row[1] else None,
                "min_rating": row[2],
                "max_rating": row[3],
            }

    def export_csv(self, path: str | Path) -> int:
        """Export all ratings to CSV. Returns count exported."""
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM ratings ORDER BY timestamp")
            rows = cursor.fetchall()

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["id", "question_id", "question_text", "answer", "rating", "comment", "timestamp"]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["id"],
                        row["question_id"],
                        row["question_text"],
                        row["answer"],
                        row["rating"],
                        row["comment"],
                        row["timestamp"],
                    ]
                )

        return len(rows)


# Default store instance
_default_store: RatingStore | None = None


def get_store() -> RatingStore:
    """Get or create the default rating store."""
    global _default_store
    if _default_store is None:
        _default_store = RatingStore()
    return _default_store


def save_rating(question_id: str, answer: str, rating: int, comment: str | None = None) -> None:
    """Convenience function to save a rating."""
    # Note: question_text not available in this simplified API
    get_store().save_rating(question_id, question_id, answer, rating, comment)


def get_history(question_id: str) -> list[dict]:
    """Get rating history as list of dicts."""
    ratings = get_store().get_history(question_id)
    return [
        {
            "rating": r.rating,
            "comment": r.comment,
            "timestamp": r.timestamp,
        }
        for r in ratings
    ]


def export_csv(path: str) -> None:
    """Export to CSV."""
    get_store().export_csv(path)
