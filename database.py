"""SQLite storage for CSE Quiz Challenge: player accounts, game history, leaderboard.

Uses only the Python standard library. Passwords are never stored in plain text:
each one is salted and hashed with PBKDF2-HMAC-SHA256.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB_FILE = Path(__file__).resolve().parent / "data" / "quiz.db"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
MIN_PASSWORD_LENGTH = 4
MAX_PASSWORD_LENGTH = 32
HASH_ITERATIONS = 200_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    salt          BLOB NOT NULL,
    password_hash BLOB NOT NULL,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);
CREATE TABLE IF NOT EXISTS games (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score         INTEGER NOT NULL,
    correct       INTEGER NOT NULL,
    answered      INTEGER NOT NULL,
    total         INTEGER NOT NULL,
    best_streak   INTEGER NOT NULL,
    grade         TEXT NOT NULL,
    difficulty    TEXT NOT NULL,
    category      TEXT NOT NULL,
    played_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id, id DESC);
"""


class AuthError(ValueError):
    """Raised with a user-friendly message when registration or login fails."""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise AuthError("Username: 3-16 letters, numbers or underscore")
    return username


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    return password


class Database:
    def __init__(self, path: Path | str = DB_FILE):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ #
    # Accounts
    # ------------------------------------------------------------------ #
    def register(self, username: str, password: str) -> dict:
        username = validate_username(username)
        validate_password(password)
        salt = os.urandom(16)
        now = _now()
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO users (username, salt, password_hash, created_at, last_login) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (username, salt, _hash_password(password, salt), now, now),
                )
        except sqlite3.IntegrityError:
            raise AuthError("That username is already taken") from None
        return {"id": cur.lastrowid, "username": username, "created_at": now}

    def authenticate(self, username: str, password: str) -> dict:
        row = self.conn.execute(
            "SELECT id, username, salt, password_hash, created_at FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        salt = row["salt"] if row else b"\0" * 16  # same work either way
        candidate = _hash_password(password, salt)
        if row is None or not hmac.compare_digest(candidate, row["password_hash"]):
            raise AuthError("Wrong username or password")
        with self.conn:
            self.conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (_now(), row["id"]))
        return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}

    def user_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # ------------------------------------------------------------------ #
    # Games
    # ------------------------------------------------------------------ #
    def record_game(self, user_id: int, *, score: int, correct: int, answered: int, total: int,
                    best_streak: int, grade: str, difficulty: str, category: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO games (user_id, score, correct, answered, total, best_streak, grade, "
                "difficulty, category, played_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, score, correct, answered, total, best_streak, grade, difficulty, category, _now()),
            )

    def user_stats(self, user_id: int) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS games, COALESCE(MAX(score), 0) AS high_score, "
            "COALESCE(MAX(best_streak), 0) AS best_streak, COALESCE(SUM(correct), 0) AS correct, "
            "COALESCE(SUM(answered), 0) AS answered FROM games WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        accuracy = round(100 * row["correct"] / row["answered"]) if row["answered"] else 0
        return {
            "games_played": row["games"],
            "high_score": row["high_score"],
            "best_streak": row["best_streak"],
            "total_correct": row["correct"],
            "accuracy": accuracy,
        }

    def recent_games(self, user_id: int, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT score, correct, answered, grade, difficulty, category, played_at "
            "FROM games WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def leaderboard(self, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT u.username AS username, MAX(g.score) AS best FROM games g "
            "JOIN users u ON u.id = g.user_id GROUP BY u.id ORDER BY best DESC, u.username LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
