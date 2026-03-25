from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import time
from typing import Callable


@dataclass(slots=True)
class ExecutionResult:
    profile: str
    command: list[str]
    stdout: str
    stderr: str
    exit_code: int
    latency_seconds: float


class CodexExecutionError(RuntimeError):
    pass


StreamHandler = Callable[[str], None]


def ensure_codex_available() -> None:
    if shutil.which("codex") is None:
        raise CodexExecutionError(
            "Could not find `codex` on PATH. Install Codex CLI before running codex-adv."
        )


def run_codex(prompt: str, profile: str, workdir: str | Path | None = None) -> ExecutionResult:
    ensure_codex_available()

    command = ["codex", "--profile", profile, prompt]
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(workdir) if workdir else None,
        text=True,
        capture_output=True,
        check=False,
    )
    latency = time.perf_counter() - started

    return ExecutionResult(
        profile=profile,
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        latency_seconds=latency,
    )


def stream_codex(
    prompt: str,
    profile: str,
    *,
    workdir: str | Path | None = None,
    on_chunk: StreamHandler | None = None,
) -> ExecutionResult:
    ensure_codex_available()

    command = ["codex", "--profile", profile, prompt]
    started = time.perf_counter()
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
    stdout = "".join(chunks)

    return ExecutionResult(
        profile=profile,
        command=command,
        stdout=stdout,
        stderr="",
        exit_code=exit_code,
        latency_seconds=latency,
    )
