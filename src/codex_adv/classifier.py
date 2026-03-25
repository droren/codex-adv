from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(slots=True)
class Classification:
    task_type: str
    complexity_score: int
    token_estimate: int


def classify_prompt(prompt: str) -> Classification:
    lowered = prompt.lower()
    words = re.findall(r"\S+", prompt)
    token_estimate = max(1, int(len(prompt) / 4))

    complexity_score = 1
    if len(words) > 30:
        complexity_score += 1
    if any(keyword in lowered for keyword in ("and", "then", "also", "plus")):
        complexity_score += 1
    if any(
        keyword in lowered
        for keyword in ("architecture", "system", "design", "multi-file", "rewrite")
    ):
        complexity_score += 2
    if any(keyword in lowered for keyword in ("tests", "refactor", "backend")):
        complexity_score += 1

    if any(keyword in lowered for keyword in ("explain", "summarize", "what does")):
        task_type = "explain"
    elif any(keyword in lowered for keyword in ("test", "pytest", "unit test")):
        task_type = "test_help" if complexity_score <= 3 else "multi_file_edit"
    elif any(keyword in lowered for keyword in ("refactor", "backend", "module")):
        task_type = "large_refactor" if complexity_score >= 4 else "single_file_edit"
    elif any(keyword in lowered for keyword in ("fix", "bug", "error")):
        task_type = "small_fix" if complexity_score <= 3 else "multi_file_edit"
    elif any(keyword in lowered for keyword in ("design", "architecture", "system")):
        task_type = "architecture"
    else:
        task_type = "unknown"

    return Classification(
        task_type=task_type,
        complexity_score=min(complexity_score, 5),
        token_estimate=token_estimate,
    )
