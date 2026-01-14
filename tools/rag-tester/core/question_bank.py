"""Question bank management for RAG testing."""

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Question:
    """A test question."""

    id: str
    category: str
    question: str
    expected: Optional[str] = None  # Gold standard answer (if known)

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["expected"] is None:
            del d["expected"]
        return d


class QuestionBank:
    """Manages a collection of test questions."""

    def __init__(self, path: str | Path | None = None):
        if path is None:
            # Default to data/questions.json relative to this file
            path = Path(__file__).parent.parent / "data" / "questions.json"
        self.path = Path(path)
        self._questions: list[Question] = []
        self._load()

    def _load(self) -> None:
        """Load questions from JSON file."""
        if not self.path.exists():
            self._questions = []
            return

        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)

        self._questions = [
            Question(
                id=q["id"],
                category=q["category"],
                question=q["question"],
                expected=q.get("expected"),
            )
            for q in data.get("questions", [])
        ]

    def _save(self) -> None:
        """Save questions to JSON file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"questions": [q.to_dict() for q in self._questions]}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_random(self, category: str | None = None) -> Question | None:
        """Get a random question, optionally filtered by category."""
        pool = self._questions
        if category:
            pool = [q for q in pool if q.category == category]
        return random.choice(pool) if pool else None

    def get_by_id(self, question_id: str) -> Question | None:
        """Get a specific question by ID."""
        for q in self._questions:
            if q.id == question_id:
                return q
        return None

    def add_question(self, question: str, category: str, expected: str | None = None) -> str:
        """Add a new question. Returns the generated ID."""
        # Generate ID: category-NNN
        existing_ids = [q.id for q in self._questions if q.category == category]
        num = len(existing_ids) + 1
        new_id = f"{category}-{num:03d}"

        # Ensure unique
        while any(q.id == new_id for q in self._questions):
            num += 1
            new_id = f"{category}-{num:03d}"

        new_q = Question(id=new_id, category=category, question=question, expected=expected)
        self._questions.append(new_q)
        self._save()
        return new_id

    def list_categories(self) -> list[str]:
        """List all unique categories."""
        return sorted({q.category for q in self._questions})

    def count(self, category: str | None = None) -> int:
        """Count questions, optionally by category."""
        if category:
            return sum(1 for q in self._questions if q.category == category)
        return len(self._questions)

    def all_questions(self, category: str | None = None) -> list[Question]:
        """Get all questions, optionally filtered by category."""
        if category:
            return [q for q in self._questions if q.category == category]
        return list(self._questions)


# Convenience functions for simple usage
_default_bank: QuestionBank | None = None


def get_bank() -> QuestionBank:
    """Get or create the default question bank."""
    global _default_bank
    if _default_bank is None:
        _default_bank = QuestionBank()
    return _default_bank


def get_random(category: str | None = None) -> dict | None:
    """Get a random question as a dict."""
    q = get_bank().get_random(category)
    return q.to_dict() if q else None


def add_question(question: str, category: str) -> str:
    """Add a question to the default bank."""
    return get_bank().add_question(question, category)


def list_categories() -> list[str]:
    """List categories in the default bank."""
    return get_bank().list_categories()
