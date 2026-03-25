from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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

    with tempfile.NamedTemporaryFile(prefix="codex-adv-", suffix=".txt", delete=False) as handle:
        output_path = Path(handle.name)

    command = _build_command(prompt, profile, output_path)
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
    finally:
        output_path.unlink(missing_ok=True)

    return ExecutionResult(
        profile=profile,
        command=command,
        stdout=final_output,
        raw_output=completed.stdout,
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

    with tempfile.NamedTemporaryFile(prefix="codex-adv-", suffix=".txt", delete=False) as handle:
        output_path = Path(handle.name)

    command = _build_command(prompt, profile, output_path)
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
    finally:
        output_path.unlink(missing_ok=True)

    return ExecutionResult(
        profile=profile,
        command=command,
        stdout=stdout,
        raw_output="".join(chunks),
        stderr="",
        exit_code=exit_code,
        latency_seconds=latency,
    )


def _build_command(prompt: str, profile: str, output_path: Path) -> list[str]:
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
