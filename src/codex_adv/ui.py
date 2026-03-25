from __future__ import annotations

from dataclasses import dataclass, field
import shutil
from typing import Any
from prompt_toolkit.formatted_text import ANSI

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.box import ROUNDED
    from rich.rule import Rule
    from rich.status import Status
    from rich.table import Table

    HAS_RICH = True
except ImportError:
    Console = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    ROUNDED = None  # type: ignore[assignment]
    Rule = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]
    HAS_RICH = False


@dataclass(slots=True)
class TerminalUI:
    use_rich: bool = True
    console: object | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.use_rich = self.use_rich and HAS_RICH
        self.console = Console() if self.use_rich else None

    def print_banner(self, session_id: str, title: str) -> None:
        text = (
            "Adaptive Codex router with local-first execution, fallback, and session memory.\n"
            "Type /help for commands."
        )
        if self.use_rich:
            self.console.print(
                Panel.fit(
                    text,
                    title="codex-adv",
                    subtitle=f"session {session_id[:8]}  {title}",
                    border_style="bright_black",
                    style="white on rgb(22,24,28)",
                    box=ROUNDED,
                )
            )
            return

        print("codex-adv interactive chat")
        print(f"session: {session_id[:8]}  title: {title}")
        print(text)

    def print_info(self, message: str) -> None:
        if self.use_rich:
            self.console.print(f"[cyan]{message}[/cyan]")
            return
        print(message)

    def print_warning(self, message: str) -> None:
        if self.use_rich:
            self.console.print(f"[yellow]{message}[/yellow]")
            return
        print(message)

    def print_error(self, message: str) -> None:
        if self.use_rich:
            self.console.print(f"[red]{message}[/red]")
            return
        print(message)

    def print_help(self, help_text: str) -> None:
        if self.use_rich:
            self.console.print(
                Panel(
                    help_text.rstrip(),
                    title="Commands",
                    border_style="bright_black",
                    style="white on rgb(18,20,24)",
                    box=ROUNDED,
                )
            )
            return
        print(help_text)

    def print_assistant_header(self, model: str) -> None:
        if self.use_rich:
            self.console.print(Rule(f"assistant [{model}]", style="bright_black"))
            return
        print(f"\nassistant [{model}]>")

    def print_debug_header(self) -> None:
        if self.use_rich:
            self.console.print(Rule("debug", style="bright_black"))
            return
        print("\ndebug>")

    def working(self, message: str) -> Any:
        if self.use_rich:
            return self.console.status(message, spinner="dots", spinner_style="bright_black")
        return _NullStatus(message)

    def stream_chunk(self, chunk: str) -> None:
        if self.use_rich:
            self.console.print(chunk, end="")
            return
        print(chunk, end="")

    def debug_chunk(self, chunk: str) -> None:
        if self.use_rich:
            self.console.print(chunk, end="", style="bright_black")
            return
        print(chunk, end="")

    def end_stream(self) -> None:
        if self.use_rich:
            self.console.print()
            return
        print()

    def print_route(self, route_line: str, rewrite: str) -> None:
        if self.use_rich:
            self.console.print(
                Panel(
                    f"{route_line}\nrewrite={rewrite}",
                    title="Route",
                    border_style="bright_black",
                    style="white on rgb(20,22,26)",
                    box=ROUNDED,
                )
            )
            return
        print(route_line)
        print(f"rewrite={rewrite}")

    def print_result(self, model: str, content: str) -> None:
        if self.use_rich:
            self.console.print(
                Panel(
                    content.rstrip(),
                    title=f"assistant [{model}]",
                    border_style="cyan",
                    style="white on rgb(16,18,22)",
                    box=ROUNDED,
                )
            )
            return
        self.print_assistant_header(model)
        print(content)

    def print_history(self, items: list[tuple[str, str]]) -> None:
        if self.use_rich:
            table = Table(title="History", show_header=True, header_style="bold cyan")
            table.add_column("Role", style="green", no_wrap=True)
            table.add_column("Content", style="white")
            for role, content in items:
                table.add_row(role, content)
            self.console.print(table)
            return
        for role, content in items:
            print(f"{role}> {content}")

    def print_sessions(self, items: list[tuple[str, str, str]]) -> None:
        if self.use_rich:
            table = Table(title="Sessions", show_header=True, header_style="bold cyan")
            table.add_column("ID", style="green")
            table.add_column("Title", style="white")
            table.add_column("Updated", style="dim")
            for session_id, title, updated_at in items:
                table.add_row(session_id, title, updated_at)
            self.console.print(table)
            return
        for session_id, title, updated_at in items:
            print(f"{session_id}  {title}  {updated_at}")

    def print_stats(self, headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
        if self.use_rich:
            table = Table(title="Routing Stats", show_header=True, header_style="bold cyan")
            for header in headers:
                table.add_column(header)
            for row in rows:
                table.add_row(*row)
            self.console.print(table)
            return
        print("\t".join(headers))
        for row in rows:
            print("\t".join(row))

    def prompt(self) -> str:
        if self.use_rich:
            return ANSI("\x1b[96myou> \x1b[0m")
        return "you> "

    def terminal_width(self) -> int:
        return shutil.get_terminal_size((100, 20)).columns


class _NullStatus:
    def __init__(self, message: str) -> None:
        self.message = message

    def __enter__(self) -> "_NullStatus":
        print(self.message)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None
