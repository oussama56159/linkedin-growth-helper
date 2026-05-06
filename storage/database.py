"""
SQLite database interface for the LinkedIn Growth System.
"""

import sqlite3
import json
import hashlib
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        schema_path = Path(__file__).parent / "schema.sql"
        with self._get_conn() as conn:
            conn.executescript(schema_path.read_text())
        logger.info("Database initialized at %s", self.db_path)

    # ── Content deduplication ──────────────────────────────────────────────

    def is_seen(self, url: str) -> bool:
        h = hashlib.md5(url.encode()).hexdigest()
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_content WHERE content_hash = ?", (h,)
            ).fetchone()
        return row is not None

    def mark_seen(self, url: str):
        h = hashlib.md5(url.encode()).hexdigest()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_content (content_hash) VALUES (?)", (h,)
            )

    # ── Posts ──────────────────────────────────────────────────────────────

    def save_post(self, post: Dict[str, Any]) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO posts
                  (post_url, author_name, author_profile_url, content,
                   likes_count, comments_count, reposts_count,
                   relevance_score, post_age_hours, hashtags, is_spam)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post["post_url"],
                    post.get("author_name"),
                    post.get("author_profile_url"),
                    post.get("content"),
                    post.get("likes_count", 0),
                    post.get("comments_count", 0),
                    post.get("reposts_count", 0),
                    post.get("relevance_score", 0.0),
                    post.get("post_age_hours"),
                    json.dumps(post.get("hashtags", [])),
                    int(post.get("is_spam", False)),
                ),
            )
        return cursor.lastrowid

    def get_top_posts(self, limit: int = 20) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM posts
                WHERE is_spam = 0
                ORDER BY relevance_score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Profiles ───────────────────────────────────────────────────────────

    def save_profile(self, profile: Dict[str, Any]) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO profiles
                  (profile_url, full_name, headline, industry, location,
                   connections_count, relevance_score, mutual_connections)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile["profile_url"],
                    profile.get("full_name"),
                    profile.get("headline"),
                    profile.get("industry"),
                    profile.get("location"),
                    profile.get("connections_count"),
                    profile.get("relevance_score", 0.0),
                    profile.get("mutual_connections", 0),
                ),
            )
        return cursor.lastrowid

    # ── Suggestions ────────────────────────────────────────────────────────

    def create_suggestion(self, suggestion: Dict[str, Any]) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO suggestions
                  (suggestion_type, target_url, target_summary, reason,
                   comment_draft, relevance_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion["suggestion_type"],
                    suggestion["target_url"],
                    suggestion.get("target_summary"),
                    suggestion.get("reason"),
                    suggestion.get("comment_draft"),
                    suggestion.get("relevance_score", 0.0),
                ),
            )
        return cursor.lastrowid

    def get_pending_suggestions(self) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM suggestions WHERE status = 'pending' ORDER BY relevance_score DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_suggestion_status(
        self,
        suggestion_id: int,
        status: str,
        telegram_message_id: Optional[int] = None,
    ):
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            if telegram_message_id is not None:
                conn.execute(
                    """
                    UPDATE suggestions
                    SET status = ?, telegram_message_id = ?,
                        notified_at = CASE WHEN status = 'pending' THEN ? ELSE notified_at END,
                        decided_at  = CASE WHEN ? IN ('approved','rejected') THEN ? ELSE decided_at END,
                        executed_at = CASE WHEN ? = 'executed' THEN ? ELSE executed_at END
                    WHERE id = ?
                    """,
                    (status, telegram_message_id, now, status, now, status, now, suggestion_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE suggestions
                    SET status = ?,
                        decided_at  = CASE WHEN ? IN ('approved','rejected') THEN ? ELSE decided_at END,
                        executed_at = CASE WHEN ? = 'executed' THEN ? ELSE executed_at END
                    WHERE id = ?
                    """,
                    (status, status, now, status, now, suggestion_id),
                )

    def get_suggestion_by_id(self, suggestion_id: int) -> Optional[Dict]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_approved_suggestions(self) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM suggestions WHERE status = 'approved' ORDER BY relevance_score DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Daily limits ───────────────────────────────────────────────────────

    def get_today_counts(self) -> Dict[str, int]:
        today = date.today().isoformat()
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM daily_limits WHERE date = ?", (today,)
            ).fetchone()
        if row:
            return dict(row)
        return {
            "date": today,
            "likes_count": 0,
            "comments_count": 0,
            "reposts_count": 0,
            "connections_count": 0,
        }

    def increment_action_count(self, action_type: str):
        """action_type: 'likes', 'comments', 'reposts', 'connections'"""
        today = date.today().isoformat()
        col = f"{action_type}_count"
        with self._get_conn() as conn:
            conn.execute(
                f"""
                INSERT INTO daily_limits (date, {col}) VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET {col} = {col} + 1
                """,
                (today,),
            )

    # ── Action log ─────────────────────────────────────────────────────────

    def log_action(
        self,
        action_type: str,
        target_url: str,
        status: str,
        suggestion_id: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO actions_log
                  (action_type, target_url, status, suggestion_id, error_message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action_type, target_url, status, suggestion_id, error_message),
            )

    def get_recent_actions(self, limit: int = 50) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM actions_log ORDER BY executed_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
