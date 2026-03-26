from __future__ import annotations

import json
import re


class DebugOutputFormatter:
    def transform(self, chunk: str) -> str:
        output: list[str] = []
        for line in chunk.splitlines():
            formatted = self._format_line(line)
            if formatted:
                output.append(formatted)
        return "".join(output)

    def _format_line(self, line: str) -> str:
        line = line.rstrip("\n")
        if not line:
            return ""

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return self._format_plain(line)

        event_type = event.get("type")
        if event_type == "thread.started":
            thread_id = event.get("thread_id", "")
            return f"session: {thread_id}\n" if thread_id else ""
        if event_type == "turn.started":
            return self._format_turn_started(event)
        if event_type == "turn.completed":
            usage = event.get("usage", {})
            if isinstance(usage, dict):
                input_tokens = int(usage.get("input_tokens", 0) or 0)
                output_tokens = int(usage.get("output_tokens", 0) or 0)
                cached = int(usage.get("cached_input_tokens", 0) or 0)
                return (
                    f"usage: in={input_tokens} out={output_tokens} cached={cached}\n"
                )
            return "turn: completed\n"
        if event_type == "item.started":
            item = event.get("item", {})
            return self._format_item_started(item)
        if event_type == "item.completed":
            item = event.get("item", {})
            return self._format_item_completed(item)
        return ""

    def _format_turn_started(self, event: dict[str, object]) -> str:
        parts: list[str] = ["turn: started"]
        cwd = str(event.get("cwd", "")).strip()
        if cwd:
            parts.append(f"cwd={cwd}")
        model = str(event.get("model", "")).strip()
        if model:
            parts.append(f"model={model}")
        provider = str(event.get("provider", "")).strip()
        if provider:
            parts.append(f"provider={provider}")
        return " | ".join(parts) + "\n"

    def _format_item_started(self, item: object) -> str:
        if not isinstance(item, dict):
            return ""
        item_type = item.get("type")
        if item_type == "web_search":
            query = item.get("query", "")
            return f"web: searching {query or '...'}\n"
        return ""

    def _format_item_completed(self, item: object) -> str:
        if not isinstance(item, dict):
            return ""
        item_type = item.get("type")
        if item_type == "error":
            message = str(item.get("message", "")).strip()
            return f"warning: {message}\n" if message else ""
        if item_type == "web_search":
            action = item.get("action", {})
            if isinstance(action, dict):
                query = action.get("query") or item.get("query", "")
                if query:
                    return f"web: searched {query}\n"
            return "web: search complete\n"
        if item_type == "reasoning":
            text = str(item.get("text", "")).strip()
            summary = self._first_meaningful_line(text)
            return f"reasoning: {summary}\n" if summary else ""
        if item_type == "command_execution":
            command = self._command_from_item(item)
            return f"exec: {command}\n" if command else "exec: running command\n"
        if item_type == "agent_message":
            text = str(item.get("text", "")).strip()
            tool_call = self._extract_tool_call(text)
            if tool_call:
                return f"{tool_call}\n"
            summary = self._first_meaningful_line(text)
            if summary:
                return f"agent: {self._truncate(summary, 140)}\n"
            return ""
        return ""

    def _format_plain(self, line: str) -> str:
        stripped = line.strip()
        if not stripped:
            return ""
        if stripped.startswith("deprecated:"):
            return f"{stripped}\n"
        if stripped.startswith("warning:"):
            return f"{stripped}\n"
        if stripped.startswith("error:"):
            return f"{stripped}\n"
        if stripped.startswith("mcp:") or stripped.startswith("mcp startup:"):
            return f"{stripped}\n"
        if stripped.startswith("[router]"):
            return f"{stripped}\n"
        if stripped.startswith("exec"):
            return f"{stripped}\n"
        return ""

    def _extract_tool_call(self, text: str) -> str | None:
        match = re.search(r'"name"\s*:\s*"exec_command".*?"cmd"\s*:\s*"([^"]+)"', text)
        if match:
            return f"exec: {match.group(1)}"
        return None

    def _command_from_item(self, item: dict[str, object]) -> str | None:
        action = item.get("action")
        if isinstance(action, dict):
            command = action.get("command")
            if command:
                return str(command)
        command = item.get("command")
        if command:
            return str(command)
        text = str(item.get("text", "")).strip()
        if text:
            return self._truncate(self._first_meaningful_line(text), 180)
        return None

    def _first_meaningful_line(self, text: str) -> str:
        for raw in text.splitlines():
            line = raw.strip(" -*\t")
            if line:
                return line
        return ""

    def _truncate(self, text: str, length: int) -> str:
        if len(text) <= length:
            return text
        return text[: length - 1].rstrip() + "..."
