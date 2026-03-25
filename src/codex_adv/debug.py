from __future__ import annotations


class DebugOutputFilter:
    def __init__(self) -> None:
        self._suppress_user_block = False

    def transform(self, chunk: str) -> str:
        output: list[str] = []
        for line in chunk.splitlines(keepends=True):
            stripped = line.strip()

            if stripped == "user":
                self._suppress_user_block = True
                continue

            if self._suppress_user_block:
                if stripped.startswith("mcp:") or stripped.startswith("mcp startup:"):
                    self._suppress_user_block = False
                    output.append(line)
                    continue
                if stripped == "codex":
                    self._suppress_user_block = False
                    output.append(line)
                    continue
                if stripped.startswith("tokens used"):
                    self._suppress_user_block = False
                    output.append(line)
                    continue
                continue

            output.append(line)

        return "".join(output)
