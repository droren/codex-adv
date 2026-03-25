from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
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


class CodexExecutionError(RuntimeError):
    pass


StreamHandler = Callable[[str], None]


def ensure_codex_available() -> None:
    if shutil.which("codex") is None:
        raise CodexExecutionError(
            "Could not find `codex` on PATH. Install Codex CLI before running codex-adv."
        )


def run_codex(prompt: str, profile: str, workdir: str | Path | None = None) -> ExecutionResult:
    return _run_codex_command(prompt, profile, workdir=workdir, session_id=None)


def resume_codex(
    prompt: str,
    session_id: str,
    workdir: str | Path | None = None,
) -> ExecutionResult:
    return _run_codex_command(prompt, None, workdir=workdir, session_id=session_id)


def _run_codex_command(
    prompt: str,
    profile: str | None,
    *,
    workdir: str | Path | None,
    session_id: str | None,
) -> ExecutionResult:
    ensure_codex_available()

    with tempfile.NamedTemporaryFile(prefix="codex-adv-", suffix=".txt", delete=False) as handle:
        output_path = Path(handle.name)

    command = _build_command(prompt, profile, output_path, session_id=session_id)
    try:
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=str(workdir) if workdir else None,
            text=True,
            capture_output=True,
            check=False,
        )
        latency = time.perf_counter() - started
        final_output = _read_final_output(output_path, completed.stdout)
        parsed_session_id = _extract_session_id(completed.stdout)
    finally:
        output_path.unlink(missing_ok=True)

    return ExecutionResult(
        profile=profile or "",
        command=command,
        stdout=final_output,
        raw_output=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        latency_seconds=latency,
        session_id=parsed_session_id or session_id,
    )


def stream_codex(
    prompt: str,
    profile: str,
    *,
    workdir: str | Path | None = None,
    on_chunk: StreamHandler | None = None,
) -> ExecutionResult:
    return _stream_codex_command(prompt, profile, workdir=workdir, on_chunk=on_chunk, session_id=None)


def stream_resume_codex(
    prompt: str,
    session_id: str,
    *,
    workdir: str | Path | None = None,
    on_chunk: StreamHandler | None = None,
) -> ExecutionResult:
    return _stream_codex_command(
        prompt,
        None,
        workdir=workdir,
        on_chunk=on_chunk,
        session_id=session_id,
    )


def _stream_codex_command(
    prompt: str,
    profile: str | None,
    *,
    workdir: str | Path | None = None,
    on_chunk: StreamHandler | None = None,
    session_id: str | None = None,
) -> ExecutionResult:
    ensure_codex_available()

    with tempfile.NamedTemporaryFile(prefix="codex-adv-", suffix=".txt", delete=False) as handle:
        output_path = Path(handle.name)

    command = _build_command(prompt, profile, output_path, session_id=session_id)
    started = time.perf_counter()
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
        for line in process.stdout:
            chunks.append(line)
            if on_chunk is not None:
                on_chunk(line)

        process.stdout.close()
        exit_code = process.wait()
        latency = time.perf_counter() - started
        stdout = _read_final_output(output_path, "".join(chunks))
        parsed_session_id = _extract_session_id("".join(chunks))
    finally:
        output_path.unlink(missing_ok=True)

    return ExecutionResult(
        profile=profile or "",
        command=command,
        stdout=stdout,
        raw_output="".join(chunks),
        stderr="",
        exit_code=exit_code,
        latency_seconds=latency,
        session_id=parsed_session_id or session_id,
    )


def _build_command(
    prompt: str,
    profile: str | None,
    output_path: Path,
    *,
    session_id: str | None,
) -> list[str]:
    if session_id:
        return [
            "codex",
            "exec",
            "resume",
            session_id,
            "-o",
            str(output_path),
            prompt,
        ]

    if profile is None:
        raise ValueError("profile is required when no session_id is provided")

    return [
        "codex",
        "exec",
        "--profile",
        profile,
        "--color",
        "never",
        "-o",
        str(output_path),
        prompt,
    ]


def _read_final_output(output_path: Path, fallback: str) -> str:
    content = output_path.read_text() if output_path.exists() else ""
    return content.strip() or fallback


def _extract_session_id(raw_output: str) -> str | None:
    match = re.search(
        r"session id:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        raw_output,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1)
