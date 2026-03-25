from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
import uuid


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    local_fast_exec_session_id TEXT NOT NULL DEFAULT '',
    local_heavy_exec_session_id TEXT NOT NULL DEFAULT '',
    cloud_exec_session_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    prompt TEXT NOT NULL,
    rewritten_prompt TEXT NOT NULL,
    task_type TEXT NOT NULL,
    complexity_score INTEGER NOT NULL,
    chosen_model TEXT NOT NULL,
    fallback_used INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL,
    latency REAL NOT NULL,
    token_estimate INTEGER NOT NULL,
    rewrite_strategy TEXT NOT NULL DEFAULT '',
    failure_reason TEXT NOT NULL DEFAULT ''
);
"""


@dataclass(slots=True)
class RequestRecord:
    timestamp: str
    prompt: str
    rewritten_prompt: str
    task_type: str
    complexity_score: int
    chosen_model: str
    fallback_used: bool
    success: bool
    latency: float
    token_estimate: int
    rewrite_strategy: str
    failure_reason: str = ""


@dataclass(slots=True)
class SessionRecord:
    id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class MessageRecord:
    session_id: str
    timestamp: str
    role: str
    content: str
    model: str = ""
    metadata: dict[str, str] | None = None


class LearningStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_session_columns(connection)

    def _ensure_session_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "local_exec_session_id" in columns and "local_fast_exec_session_id" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN local_fast_exec_session_id TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "UPDATE sessions SET local_fast_exec_session_id = local_exec_session_id WHERE local_exec_session_id != ''"
            )
            columns.add("local_fast_exec_session_id")
        if "local_fast_exec_session_id" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN local_fast_exec_session_id TEXT NOT NULL DEFAULT ''"
            )
            columns.add("local_fast_exec_session_id")
        if "local_heavy_exec_session_id" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN local_heavy_exec_session_id TEXT NOT NULL DEFAULT ''"
            )
            columns.add("local_heavy_exec_session_id")
        if "cloud_exec_session_id" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN cloud_exec_session_id TEXT NOT NULL DEFAULT ''"
            )

    def create_session(self, title: str, timestamp: str) -> SessionRecord:
        session = SessionRecord(
            id=str(uuid.uuid4()),
            title=title,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (session.id, session.title, session.created_at, session.updated_at),
            )
        return session

    def update_session_timestamp(self, session_id: str, timestamp: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (timestamp, session_id),
            )

    def list_sessions(self, limit: int = 10) -> list[sqlite3.Row]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

    def get_exec_session_id(self, session_id: str, route: str) -> str | None:
        column = self._route_column(route)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {column} FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if not row or not row[0]:
            return None
        return str(row[0])

    def set_exec_session_id(self, session_id: str, route: str, exec_session_id: str) -> None:
        column = self._route_column(route)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE sessions SET {column} = ? WHERE id = ?",
                (exec_session_id, session_id),
            )

    def clear_exec_session_id(self, session_id: str, route: str) -> None:
        self.set_exec_session_id(session_id, route, "")

    def find_session_by_prefix(self, session_prefix: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM sessions
                WHERE id LIKE ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (f"{session_prefix}%",),
            ).fetchone()

    def rename_session(self, session_id: str, title: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )

    def latest_session_id(self) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        return row[0] if row else None

    def add_message(self, record: MessageRecord) -> None:
        payload = json.dumps(record.metadata or {}, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (session_id, timestamp, role, content, model, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.session_id,
                    record.timestamp,
                    record.role,
                    record.content,
                    record.model,
                    payload,
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (record.timestamp, record.session_id),
            )

    def _route_column(self, route: str) -> str:
        if route == "local":
            return "local_fast_exec_session_id"
        if route == "local_fast":
            return "local_fast_exec_session_id"
        if route == "local_heavy":
            return "local_heavy_exec_session_id"
        if route == "cloud":
            return "cloud_exec_session_id"
        raise ValueError(f"Unknown route: {route}")

    def get_messages(self, session_id: str, limit: int | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT session_id, timestamp, role, content, model, metadata_json
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
        """
        parameters: tuple[object, ...] = (session_id,)
        if limit is not None:
            query += " LIMIT ?"
            parameters = (session_id, limit)

        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(query, parameters).fetchall()

    def log_request(self, record: RequestRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO requests (
                    timestamp,
                    prompt,
                    rewritten_prompt,
                    task_type,
                    complexity_score,
                    chosen_model,
                    fallback_used,
                    success,
                    latency,
                    token_estimate,
                    rewrite_strategy,
                    failure_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.timestamp,
                    record.prompt,
                    record.rewritten_prompt,
                    record.task_type,
                    record.complexity_score,
                    record.chosen_model,
                    int(record.fallback_used),
                    int(record.success),
                    record.latency,
                    record.token_estimate,
                    record.rewrite_strategy,
                    record.failure_reason,
                ),
            )

    def success_rate(self, model: str, task_type: str) -> float | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT AVG(success)
                FROM requests
                WHERE chosen_model = ? AND task_type = ?
                """,
                (model, task_type),
            ).fetchone()

        value = row[0] if row else None
        if value is None:
            return None
        return float(value)

    def summary(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT
                    chosen_model,
                    task_type,
                    COUNT(*) AS total_requests,
                    ROUND(AVG(success), 3) AS success_rate,
                    ROUND(AVG(latency), 3) AS avg_latency,
                    SUM(fallback_used) AS fallbacks
                FROM requests
                GROUP BY chosen_model, task_type
                ORDER BY total_requests DESC, chosen_model, task_type
                """
            ).fetchall()
