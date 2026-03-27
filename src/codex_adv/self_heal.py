from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codex_adv.config import AppConfig
from codex_adv.executor import ExecutorSettings, run_codex

SELF_HEAL_ATTEMPTS_ENV = "CODEX_ADV_SELF_HEAL_ATTEMPTS"


@dataclass(slots=True)
class CrashContext:
    command: str
    workdir: str
    session_id: str = ""
    last_prompt: str = ""


class SelfHealingManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def attempt_recovery(
        self,
        exc: Exception,
        context: CrashContext,
        *,
        ui: object | None = None,
    ) -> bool:
        attempts = int(os.environ.get(SELF_HEAL_ATTEMPTS_ENV, "0") or 0)
        incident_path = self._record_incident(exc, context)
        self._ui_info(
            ui,
            f"internal error captured in {incident_path}. starting self-healing investigation...",
        )

        if attempts >= 1:
            self._ui_error(
                ui,
                "self-healing already attempted once in this process chain. not retrying again.",
            )
            return False

        summary = self._run_recovery(incident_path)
        if not summary:
            self._ui_error(ui, "self-healing investigation did not produce a usable recovery.")
            return False

        self._append_recovery_summary(incident_path, summary)
        self._ui_info(
            ui,
            "self-healing applied a recovery attempt. "
            "restarting into a fresh instance...",
        )
        self._restart_process()
        return True

    def _run_recovery(self, incident_path: Path) -> str:
        incident = json.loads(incident_path.read_text())
        prompt = (
            "You are recovering codex-adv after an internal crash.\n"
            "Investigate the incident, inspect the codebase, "
            "apply the smallest safe fix if you can, "
            "and then return a short summary of what you changed "
            "and why restart is appropriate.\n\n"
            f"Incident file: {incident_path}\n"
            f"Command: {incident['command']}\n"
            f"Session id: {incident.get('session_id', '')}\n"
            f"Last prompt: {incident.get('last_prompt', '')}\n\n"
            "Traceback:\n"
            f"{incident['traceback']}\n"
        )
        result = run_codex(
            prompt,
            self.config.profiles.cloud,
            workdir=incident["workdir"],
            settings=ExecutorSettings(
                dangerous_bypass_approvals_and_sandbox=(
                    self.config.execution.dangerous_bypass_approvals_and_sandbox
                ),
                ephemeral_codex_sessions=True,
            ),
        )
        if result.exit_code != 0:
            return ""
        return result.stdout.strip()

    def _record_incident(self, exc: Exception, context: CrashContext) -> Path:
        incident_dir = Path(".codex-adv/incidents")
        incident_dir.mkdir(parents=True, exist_ok=True)
        incident_name = (
            f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
            f"-{uuid.uuid4().hex[:8]}.json"
        )
        incident_path = incident_dir / incident_name
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "command": context.command,
            "workdir": context.workdir,
            "session_id": context.session_id,
            "last_prompt": context.last_prompt,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": "".join(traceback.format_exception(exc)),
        }
        incident_path.write_text(json.dumps(payload, indent=2))
        return incident_path

    def _append_recovery_summary(self, incident_path: Path, summary: str) -> None:
        payload = json.loads(incident_path.read_text())
        payload["recovery_summary"] = summary
        incident_path.write_text(json.dumps(payload, indent=2))

    def _restart_process(self) -> None:
        env = dict(os.environ)
        attempts = int(env.get(SELF_HEAL_ATTEMPTS_ENV, "0") or 0)
        env[SELF_HEAL_ATTEMPTS_ENV] = str(attempts + 1)
        os.execvpe(  # nosec B606
            sys.executable,
            [sys.executable, sys.argv[0], *sys.argv[1:]],
            env,
        )

    def _ui_info(self, ui: object | None, message: str) -> None:
        if ui is not None and hasattr(ui, "print_info"):
            ui.print_info(message)
            return
        print(message)

    def _ui_error(self, ui: object | None, message: str) -> None:
        if ui is not None and hasattr(ui, "print_error"):
            ui.print_error(message)
            return
        print(message, file=sys.stderr)
