from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Callable


@dataclass(slots=True)
class ExecutionResult:
    profile: str
    command: list[str]
    stdout: str
    raw_output: str
    stderr: str
    exit_code: int
    latency_seconds: float
    session_id: str | None
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    interrupted: bool


class CodexExecutionError(RuntimeError):
    pass


StreamHandler = Callable[[str], None]


@dataclass(slots=True)
class ExecutorSettings:
    web_search: str = "disabled"
    dangerous_bypass_approvals_and_sandbox: bool = False


def ensure_codex_available() -> None:
    if shutil.which("codex") is None:
        raise CodexExecutionError(
            "Could not find `codex` on PATH. Install Codex CLI before running codex-adv."
        )


def run_codex(
    prompt: str,
    profile: str,
    workdir: str | Path | None = None,
    settings: ExecutorSettings | None = None,
    cancel_event: threading.Event | None = None,
) -> ExecutionResult:
    return _run_codex_command(
        prompt,
        profile,
        workdir=workdir,
        session_id=None,
        settings=settings,
        cancel_event=cancel_event,
    )


def resume_codex(
    prompt: str,
    session_id: str,
    workdir: str | Path | None = None,
    settings: ExecutorSettings | None = None,
    cancel_event: threading.Event | None = None,
) -> ExecutionResult:
    return _run_codex_command(
        prompt,
        None,
        workdir=workdir,
        session_id=session_id,
        settings=settings,
        cancel_event=cancel_event,
    )


def _run_codex_command(
    prompt: str,
    profile: str | None,
    *,
    workdir: str | Path | None,
    session_id: str | None,
    settings: ExecutorSettings | None,
    cancel_event: threading.Event | None,
) -> ExecutionResult:
    return _stream_codex_command(
        prompt,
        profile,
        workdir=workdir,
        on_chunk=None,
        session_id=session_id,
        settings=settings,
        cancel_event=cancel_event,
    )


def stream_codex(
    prompt: str,
    profile: str,
    *,
    workdir: str | Path | None = None,
    on_chunk: StreamHandler | None = None,
    settings: ExecutorSettings | None = None,
    cancel_event: threading.Event | None = None,
) -> ExecutionResult:
    return _stream_codex_command(
        prompt,
        profile,
        workdir=workdir,
        on_chunk=on_chunk,
        session_id=None,
        settings=settings,
        cancel_event=cancel_event,
    )


def stream_resume_codex(
    prompt: str,
    session_id: str,
    *,
    workdir: str | Path | None = None,
    on_chunk: StreamHandler | None = None,
    settings: ExecutorSettings | None = None,
    cancel_event: threading.Event | None = None,
) -> ExecutionResult:
    return _stream_codex_command(
        prompt,
        None,
        workdir=workdir,
        on_chunk=on_chunk,
        session_id=session_id,
        settings=settings,
        cancel_event=cancel_event,
    )


def _stream_codex_command(
    prompt: str,
    profile: str | None,
    *,
    workdir: str | Path | None = None,
    on_chunk: StreamHandler | None = None,
    session_id: str | None = None,
    settings: ExecutorSettings | None = None,
    cancel_event: threading.Event | None = None,
) -> ExecutionResult:
    ensure_codex_available()

    with tempfile.NamedTemporaryFile(prefix="codex-adv-", suffix=".txt", delete=False) as handle:
        output_path = Path(handle.name)

    command = _build_command(
        prompt,
        profile,
        output_path,
        session_id=session_id,
        settings=settings or ExecutorSettings(),
    )
    started = time.perf_counter()
    interrupted = False
    try:
        process = subprocess.Popen(
            command,
            cwd=str(workdir) if workdir else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )

        chunks: list[str] = []
        assert process.stdout is not None
        stdout_fd = process.stdout.fileno()

        while True:
            if cancel_event is not None and cancel_event.is_set() and process.poll() is None:
                interrupted = True
                process.terminate()
            ready, _, _ = select.select([stdout_fd], [], [], 0.1)
            if ready:
                line = process.stdout.readline()
                if line:
                    chunks.append(line)
                    if on_chunk is not None:
                        on_chunk(line)
            if process.poll() is not None:
                # Drain remaining buffered lines after process exit.
                remaining = process.stdout.read()
                if remaining:
                    chunks.append(remaining)
                    if on_chunk is not None:
                        on_chunk(remaining)
                break

        process.stdout.close()
        exit_code = process.wait()
        latency = time.perf_counter() - started
        raw_output = "".join(chunks)
        stdout = _read_final_output(output_path, raw_output)
        parsed_session_id = _extract_session_id(raw_output)
        usage = _extract_usage(raw_output)
    finally:
        output_path.unlink(missing_ok=True)

    return ExecutionResult(
        profile=profile or "",
        command=command,
        stdout=stdout,
        raw_output=raw_output,
        stderr="",
        exit_code=exit_code,
        latency_seconds=latency,
        session_id=parsed_session_id or session_id,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cached_input_tokens=usage["cached_input_tokens"],
        interrupted=interrupted,
    )


def _build_command(
    prompt: str,
    profile: str | None,
    output_path: Path,
    *,
    session_id: str | None,
    settings: ExecutorSettings,
) -> list[str]:
    config_flags: list[str] = []
    if settings.web_search != "disabled":
        config_flags.extend(["-c", f'web_search="{settings.web_search}"'])
    if settings.dangerous_bypass_approvals_and_sandbox:
        config_flags.append("--dangerously-bypass-approvals-and-sandbox")

    if session_id:
        return [
            "codex",
            "exec",
            "resume",
            *config_flags,
            session_id,
            "--json",
            "-o",
            str(output_path),
            prompt,
        ]

    if profile is None:
        raise ValueError("profile is required when no session_id is provided")

    return [
        "codex",
        "exec",
        *config_flags,
        "--profile",
        profile,
        "--json",
        "-o",
        str(output_path),
        prompt,
    ]


def _read_final_output(output_path: Path, fallback: str) -> str:
    content = output_path.read_text() if output_path.exists() else ""
    return content.strip() or fallback


def _extract_session_id(raw_output: str) -> str | None:
    for line in raw_output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str):
                return thread_id
    match = re.search(
        r"session id:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        raw_output,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1)


def _extract_usage(raw_output: str) -> dict[str, int]:
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
    }
    for line in raw_output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "turn.completed":
            continue
        payload = event.get("usage", {})
        if not isinstance(payload, dict):
            continue
        usage["input_tokens"] = int(payload.get("input_tokens", 0) or 0)
        usage["output_tokens"] = int(payload.get("output_tokens", 0) or 0)
        usage["cached_input_tokens"] = int(payload.get("cached_input_tokens", 0) or 0)
    return usage
