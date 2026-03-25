from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import shlex

from codex_adv.input import ChatInput
from codex_adv.learning import LearningStore, MessageRecord, SessionRecord
from codex_adv.router import Router, RoutedResponse
from codex_adv.ui import TerminalUI


HELP_TEXT = """Commands:
/help                Show this help
/quit                Exit chat
/exit                Exit chat
/new [title]         Start a new session
/debug [on|off]      Toggle execution debug output
/switch <id-prefix>  Switch to another recent session
/rename <title>      Rename the current session
/session             Show current session id and title
/sessions            List recent sessions
/history [n]         Show messages in this session
/stats               Show routing stats
/route               Show details for the last routed turn
/clear               Clear the screen
"""


@dataclass(slots=True)
class ChatState:
    session: SessionRecord
    last_response: RoutedResponse | None = None
    debug_enabled: bool = False


class InteractiveChat:
    def __init__(self, router: Router, store: LearningStore) -> None:
        self.router = router
        self.store = store
        self.ui = TerminalUI()
        self.input = ChatInput(Path(".codex-adv/input-history.txt"))

    def start(self, resume_latest: bool = True) -> int:
        state = self._load_or_create_session(resume_latest=resume_latest)
        self._print_banner(state)

        while True:
            try:
                raw = self.input.prompt(self.ui.prompt()).strip()
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                self.ui.print_warning("Use /quit to exit.")
                continue

            if not raw:
                continue

            if raw.startswith("/"):
                should_continue = self._handle_command(raw, state)
                if not should_continue:
                    return 0
                continue

            self._run_turn(raw, state)

    def _load_or_create_session(self, resume_latest: bool) -> ChatState:
        if resume_latest:
            latest_id = self.store.latest_session_id()
            if latest_id:
                row = self.store.get_session(latest_id)
                if row is not None:
                    session = SessionRecord(
                        id=row["id"],
                        title=row["title"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    return ChatState(session=session)

        session = self._create_session("Interactive session")
        return ChatState(session=session)

    def _create_session(self, title: str) -> SessionRecord:
        timestamp = datetime.now(UTC).isoformat()
        return self.store.create_session(title=title, timestamp=timestamp)

    def _print_banner(self, state: ChatState) -> None:
        self.ui.print_banner(state.session.id, state.session.title)

    def _handle_command(self, raw: str, state: ChatState) -> bool:
        parts = shlex.split(raw)
        command = parts[0]

        if command in {"/quit", "/exit"}:
            return False
        if command == "/help":
            self.ui.print_help(HELP_TEXT)
            return True
        if command == "/debug":
            if len(parts) == 1:
                state.debug_enabled = not state.debug_enabled
            elif parts[1].lower() in {"on", "off"}:
                state.debug_enabled = parts[1].lower() == "on"
            else:
                self.ui.print_warning("Usage: /debug [on|off]")
                return True
            self.ui.print_info(f"debug: {'on' if state.debug_enabled else 'off'}")
            return True
        if command == "/session":
            self.ui.print_info(f"{state.session.id}  {state.session.title}")
            return True
        if command == "/sessions":
            rows = self.store.list_sessions()
            self.ui.print_sessions(
                [(row["id"], row["title"], row["updated_at"]) for row in rows]
            )
            return True
        if command == "/history":
            limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            self._print_history(state.session.id, limit=limit)
            return True
        if command == "/stats":
            rows = self.store.summary()
            if not rows:
                self.ui.print_info("No routing history yet.")
                return True
            table_rows = [
                (
                    str(row["chosen_model"]),
                    str(row["task_type"]),
                    str(row["total_requests"]),
                    str(row["success_rate"]),
                    str(row["avg_latency"]),
                    str(row["fallbacks"]),
                )
                for row in rows
            ]
            self.ui.print_stats(
                ("model", "task_type", "total", "success_rate", "avg_latency", "fallbacks"),
                table_rows,
            )
            return True
        if command == "/route":
            self._print_last_route(state.last_response)
            return True
        if command == "/new":
            title = " ".join(parts[1:]).strip() or "Interactive session"
            state.session = self._create_session(title)
            state.last_response = None
            self.ui.print_info(
                f"new session: {state.session.id[:8]}  title: {state.session.title}"
            )
            return True
        if command == "/rename":
            title = " ".join(parts[1:]).strip()
            if not title:
                self.ui.print_warning("Usage: /rename <title>")
                return True
            self.store.rename_session(state.session.id, title)
            state.session = SessionRecord(
                id=state.session.id,
                title=title,
                created_at=state.session.created_at,
                updated_at=state.session.updated_at,
            )
            self.ui.print_info(f"renamed session to: {title}")
            return True
        if command == "/switch":
            if len(parts) < 2:
                self.ui.print_warning("Usage: /switch <id-prefix>")
                return True
            session = self.store.find_session_by_prefix(parts[1])
            if session is None:
                self.ui.print_warning("No session matched that prefix.")
                return True
            state.session = SessionRecord(
                id=session["id"],
                title=session["title"],
                created_at=session["created_at"],
                updated_at=session["updated_at"],
            )
            state.last_response = None
            self.ui.print_info(
                f"switched to: {state.session.id[:8]}  {state.session.title}"
            )
            return True
        if command == "/clear":
            os.system("clear")
            return True

        self.ui.print_warning(f"Unknown command: {command}. Type /help for commands.")
        return True

    def _run_turn(self, prompt: str, state: ChatState) -> None:
        timestamp = datetime.now(UTC).isoformat()
        self.store.add_message(
            MessageRecord(
                session_id=state.session.id,
                timestamp=timestamp,
                role="user",
                content=prompt,
            )
        )
        history = self.store.get_messages(state.session.id)
        self.ui.print_assistant_header("working")
        if state.debug_enabled:
            self.ui.print_debug_header()
        with self.ui.working(self._working_message(prompt, state)):
            response = self.router.run(
                prompt,
                conversation=history[:-1],
                stream_handler=self.ui.debug_chunk if state.debug_enabled else None,
            )
        state.last_response = response

        response_timestamp = datetime.now(UTC).isoformat()
        self.store.add_message(
            MessageRecord(
                session_id=state.session.id,
                timestamp=response_timestamp,
                role="assistant",
                content=response.output,
                model=response.final_model,
                metadata={
                    "task_type": response.classification.task_type,
                    "complexity": str(response.classification.complexity_score),
                    "fallback_used": str(response.fallback_used).lower(),
                },
            )
        )

        self.ui.print_result(response.final_model, response.output)
        if not response.success:
            self.ui.print_warning(f"request ended with {response.failure_reason}")

    def _print_history(self, session_id: str, limit: int | None = None) -> None:
        rows = self.store.get_messages(session_id)
        if not rows:
            self.ui.print_info("No messages in this session yet.")
            return

        selected = rows[-limit:] if limit is not None else rows
        items: list[tuple[str, str]] = []
        for row in selected:
            role = row["role"]
            model = row["model"]
            label = role if not model else f"{role}:{model}"
            items.append((label, row["content"]))
        self.ui.print_history(items)

    def _print_last_route(self, response: RoutedResponse | None) -> None:
        if response is None:
            self.ui.print_info("No routed turn yet.")
            return

        route_line = (
            f"initial={response.initial_model} final={response.final_model} "
            f"fallback={str(response.fallback_used).lower()} "
            f"task={response.classification.task_type} "
            f"complexity={response.classification.complexity_score} "
            f"latency={response.latency_seconds:.2f}s"
        )
        self.ui.print_route(route_line, response.rewrite_strategy)

    def _working_message(self, prompt: str, state: ChatState) -> str:
        task = "local-first routing"
        return f"{task} for session {state.session.id[:8]}..."
