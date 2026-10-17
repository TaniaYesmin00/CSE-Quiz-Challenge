"""Game logic for CSE Quiz Challenge.

This module has no pygame dependency, so everything here can be unit-tested
without opening a window. The UI in ``main.py`` only draws what this module
reports.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "questions.json"

DIFFICULTIES = ("All", "Easy", "Medium", "Hard")
ROUND_LENGTH = 10
QUESTION_SECONDS = 20.0
STARTING_LIVES = 3
BASE_POINTS = 100
STREAK_BONUS = 20
MAX_STREAK_BONUS_STEPS = 5
TIME_BONUS_MAX = 50


# --------------------------------------------------------------------------- #
# Loading and saving
# --------------------------------------------------------------------------- #
def validate_questions(data) -> list[dict]:
    """Return ``data`` if it is a valid question list, otherwise raise ValueError."""
    if not isinstance(data, list) or not data:
        raise ValueError("Question file must contain a non-empty list.")
    for number, q in enumerate(data, start=1):
        if not isinstance(q, dict):
            raise ValueError(f"Question #{number} is not an object.")
        for key in ("question", "options", "answer", "category", "difficulty"):
            if key not in q:
                raise ValueError(f"Question #{number} is missing '{key}'.")
        if q["difficulty"] not in DIFFICULTIES[1:]:
            raise ValueError(f"Question #{number} has invalid difficulty '{q['difficulty']}'.")
        if not isinstance(q["options"], list) or not 2 <= len(q["options"]) <= 4:
            raise ValueError(f"Question #{number} must have 2 to 4 options.")
        if len(set(q["options"])) != len(q["options"]):
            raise ValueError(f"Question #{number} has duplicate options.")
        if not isinstance(q["answer"], int) or not 0 <= q["answer"] < len(q["options"]):
            raise ValueError(f"Question #{number} has an invalid answer index.")
    return data


def load_questions(path: Path = DATA_FILE) -> list[dict]:
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            return validate_questions(json.load(f))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Could not load questions from {path}: {exc}") from exc


def list_categories(questions: list[dict]) -> list[str]:
    return ["All"] + sorted({q["category"] for q in questions})


def count_matching(questions: list[dict], difficulty: str = "All", category: str = "All") -> int:
    """How many questions match the chosen filters."""
    return sum(
        (difficulty == "All" or q["difficulty"] == difficulty)
        and (category == "All" or q["category"] == category)
        for q in questions
    )


# --------------------------------------------------------------------------- #
# A single round
# --------------------------------------------------------------------------- #
@dataclass
class AnswerResult:
    correct: bool
    timed_out: bool
    points: int
    correct_index: int


@dataclass
class Round:
    """State of one quiz round."""

    questions: list[dict]
    lives: int = STARTING_LIVES
    score: int = 0
    streak: int = 0
    best_streak: int = 0
    index: int = 0
    correct_count: int = 0
    time_left: float = QUESTION_SECONDS
    fifty_used: bool = False
    removed: set = field(default_factory=set)
    missed: list = field(default_factory=list)
    locked: bool = False
    selected: Optional[int] = None

    # -- helpers ------------------------------------------------------------ #
    @property
    def total(self) -> int:
        return len(self.questions)

    @property
    def current(self) -> dict:
        return self.questions[self.index]

    @property
    def finished(self) -> bool:
        return self.lives <= 0 or (self.locked and self.index >= self.total - 1)

    @property
    def answered(self) -> int:
        return self.index + (1 if self.locked else 0)

    @property
    def accuracy(self) -> int:
        return round(100 * self.correct_count / self.answered) if self.answered else 0

    @property
    def grade(self) -> str:
        return grade_for(self.correct_count, self.total, self.lives)

    # -- actions ------------------------------------------------------------ #
    def tick(self, dt: float) -> bool:
        """Advance the timer. Returns True when time has just run out."""
        if self.locked:
            return False
        self.time_left = max(0.0, self.time_left - dt)
        return self.time_left <= 0.0

    def answer(self, choice: int) -> AnswerResult:
        """Lock in an answer. ``choice`` of -1 means the timer ran out."""
        if self.locked:
            raise RuntimeError("Question already answered.")
        q = self.current
        correct_index = q["answer"]
        self.locked = True
        self.selected = choice if choice >= 0 else None
        timed_out = choice < 0
        if not timed_out and choice == correct_index:
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.correct_count += 1
            points = (
                BASE_POINTS
                + min(self.streak - 1, MAX_STREAK_BONUS_STEPS) * STREAK_BONUS
                + int(TIME_BONUS_MAX * self.time_left / QUESTION_SECONDS)
            )
            self.score += points
            return AnswerResult(True, False, points, correct_index)
        self.streak = 0
        self.lives -= 1
        self.missed.append(
            {
                "question": q["question"],
                "category": q["category"],
                "correct": q["options"][correct_index],
                "chosen": q["options"][choice] if choice >= 0 else None,
            }
        )
        return AnswerResult(False, timed_out, 0, correct_index)

    def advance(self) -> bool:
        """Move to the next question. Returns False if the round is over."""
        if self.finished:
            return False
        self.index += 1
        self.time_left = QUESTION_SECONDS
        self.locked = False
        self.selected = None
        self.removed = set()
        return True

    def use_fifty_fifty(self) -> set:
        """Remove two wrong options. One use per round."""
        if self.fifty_used or self.locked:
            return set()
        wrong = [i for i in range(len(self.current["options"])) if i != self.current["answer"]]
        if len(wrong) < 3:
            return set()
        self.fifty_used = True
        self.removed = set(random.sample(wrong, 2))
        return self.removed


def grade_for(correct: int, total: int, lives: int) -> str:
    if total <= 0:
        return "C"
    ratio = correct / total
    if ratio >= 0.9 and lives > 0:
        return "S"
    if ratio >= 0.75:
        return "A"
    if ratio >= 0.5:
        return "B"
    return "C"


def build_round(
    questions: list[dict],
    difficulty: str = "All",
    category: str = "All",
    length: int = ROUND_LENGTH,
    rng: Optional[random.Random] = None,
) -> Round:
    """Pick questions for a round and shuffle each question's options."""
    rng = rng or random.Random()
    pool = [
        q
        for q in questions
        if (difficulty == "All" or q["difficulty"] == difficulty)
        and (category == "All" or q["category"] == category)
    ]
    if not pool:  # filters too strict: fall back to everything
        pool = list(questions)
    rng.shuffle(pool)
    picked = []
    for q in pool[: min(length, len(pool))]:
        order = list(range(len(q["options"])))
        rng.shuffle(order)
        picked.append(
            {
                "question": q["question"],
                "category": q["category"],
                "difficulty": q["difficulty"],
                "options": [q["options"][i] for i in order],
                "answer": order.index(q["answer"]),
            }
        )
    return Round(questions=picked)
