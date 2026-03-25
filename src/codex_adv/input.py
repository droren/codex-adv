from __future__ import annotations

from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.shortcuts import CompleteStyle


COMMANDS: tuple[tuple[str, str], ...] = (
    ("/help", "Show help"),
    ("/quit", "Exit chat"),
    ("/exit", "Exit chat"),
    ("/new", "Start a new session"),
    ("/switch", "Switch sessions by id prefix"),
    ("/rename", "Rename current session"),
    ("/session", "Show current session"),
    ("/sessions", "List recent sessions"),
    ("/history", "Show chat history"),
    ("/stats", "Show routing stats"),
    ("/usage", "Show session token usage"),
    ("/route", "Show last route"),
    ("/clear", "Clear the screen"),
)


class SlashCommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        for command, meta in COMMANDS:
            if command.startswith(text):
                yield Completion(
                    command,
                    start_position=-len(text),
                    display=command,
                    display_meta=meta,
                )


class ChatInput:
    def __init__(
        self,
        history_path: str | Path,
        bottom_toolbar: Callable[[], str] | None = None,
    ) -> None:
        path = Path(history_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(str(path)),
            completer=SlashCommandCompleter(),
            complete_while_typing=True,
            complete_style=CompleteStyle.MULTI_COLUMN,
            reserve_space_for_menu=8,
            bottom_toolbar=bottom_toolbar,
        )

    def prompt(self, message: str) -> str:
        return self.session.prompt(message)
