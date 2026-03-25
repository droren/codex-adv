from __future__ import annotations

from dataclasses import dataclass

from codex_adv.classifier import Classification


@dataclass(slots=True)
class RewriteResult:
    rewritten_prompt: str
    strategy: str


def rewrite_for_local(prompt: str, classification: Classification, style: str) -> RewriteResult:
    rewritten = (
        "Keep scope tight. Solve only the immediate request. "
        "Prefer one file at a time. Return concise output with concrete changes.\n\n"
        f"Task type: {classification.task_type}\n"
        f"Original request:\n{prompt}"
    )
    return RewriteResult(rewritten_prompt=rewritten, strategy=style)


def rewrite_for_cloud(prompt: str, classification: Classification, style: str) -> RewriteResult:
    rewritten = (
        "Break this into clear steps, keep the implementation complete, and prefer a high-success plan. "
        "If code changes are needed, structure the work and return actionable output.\n\n"
        f"Task type: {classification.task_type}\n"
        f"Complexity: {classification.complexity_score}/5\n"
        f"Original request:\n{prompt}"
    )
    return RewriteResult(rewritten_prompt=rewritten, strategy=style)
