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
    session_id TEXT NOT NULL DEFAULT '',
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
    actual_tokens_used INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    rewrite_strategy TEXT NOT NULL DEFAULT '',
    failure_reason TEXT NOT NULL DEFAULT ''
);
"""


@dataclass(slots=True)
class RequestRecord:
    session_id: str
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
    actual_tokens_used: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
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
            self._ensure_request_columns(connection)

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

    def _ensure_request_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(requests)").fetchall()
        }
        if "session_id" not in columns:
            connection.execute(
                "ALTER TABLE requests ADD COLUMN session_id TEXT NOT NULL DEFAULT ''"
            )
        if "actual_tokens_used" not in columns:
            connection.execute(
                "ALTER TABLE requests ADD COLUMN actual_tokens_used INTEGER NOT NULL DEFAULT 0"
            )
        if "input_tokens" not in columns:
            connection.execute(
                "ALTER TABLE requests ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0"
            )
        if "output_tokens" not in columns:
            connection.execute(
                "ALTER TABLE requests ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0"
            )
        if "cached_input_tokens" not in columns:
            connection.execute(
                "ALTER TABLE requests ADD COLUMN cached_input_tokens INTEGER NOT NULL DEFAULT 0"
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
                    session_id,
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
                    actual_tokens_used,
                    input_tokens,
                    output_tokens,
                    cached_input_tokens,
                    rewrite_strategy,
                    failure_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.session_id,
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
                    record.actual_tokens_used,
                    record.input_tokens,
                    record.output_tokens,
                    record.cached_input_tokens,
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
                    SUM(fallback_used) AS fallbacks,
                    SUM(actual_tokens_used) AS actual_tokens_used,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(cached_input_tokens) AS cached_input_tokens
                FROM requests
                GROUP BY chosen_model, task_type
                ORDER BY total_requests DESC, chosen_model, task_type
                """
            ).fetchall()

    def session_usage(self, session_id: str) -> list[sqlite3.Row]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT
                    chosen_model,
                    COUNT(*) AS total_requests,
                    SUM(actual_tokens_used) AS actual_tokens_used,
                    SUM(input_tokens) AS input_tokens,
                    SUM(output_tokens) AS output_tokens,
                    SUM(cached_input_tokens) AS cached_input_tokens,
                    ROUND(AVG(latency), 3) AS avg_latency,
                    SUM(fallback_used) AS fallbacks
                FROM requests
                WHERE session_id = ?
                GROUP BY chosen_model
                ORDER BY total_requests DESC, chosen_model
                """,
                (session_id,),
            ).fetchall()

    def session_usage_totals(self, session_id: str) -> sqlite3.Row:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT
                    COUNT(*) AS total_requests,
                    COALESCE(SUM(actual_tokens_used), 0) AS actual_tokens_used,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                    ROUND(COALESCE(AVG(latency), 0), 3) AS avg_latency,
                    COALESCE(SUM(CASE WHEN chosen_model LIKE 'cloud%' THEN actual_tokens_used ELSE 0 END), 0) AS cloud_tokens,
                    COALESCE(SUM(CASE WHEN chosen_model LIKE 'local%' THEN actual_tokens_used ELSE 0 END), 0) AS local_tokens,
                    COALESCE(SUM(CASE WHEN chosen_model LIKE 'cloud%' THEN input_tokens ELSE 0 END), 0) AS cloud_input_tokens,
                    COALESCE(SUM(CASE WHEN chosen_model LIKE 'cloud%' THEN output_tokens ELSE 0 END), 0) AS cloud_output_tokens,
                    COALESCE(SUM(CASE WHEN chosen_model LIKE 'local%' THEN input_tokens ELSE 0 END), 0) AS local_input_tokens,
                    COALESCE(SUM(CASE WHEN chosen_model LIKE 'local%' THEN output_tokens ELSE 0 END), 0) AS local_output_tokens
                FROM requests
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
