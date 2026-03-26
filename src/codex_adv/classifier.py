from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(slots=True)
class Classification:
    task_type: str
    complexity_score: int
    token_estimate: int
    requires_web: bool = False


def classify_prompt(prompt: str) -> Classification:
    lowered = prompt.lower()
    words = re.findall(r"\S+", prompt)
    token_estimate = max(1, int(len(prompt) / 4))
    requires_web = any(
        keyword in lowered
        for keyword in (
            "latest news",
            "current news",
            "news in the world",
            "search the web",
            "search for",
            "look up",
            "browse",
            "web search",
            "current events",
            "what's happening",
            "what is happening",
            "today's news",
            "latest headlines",
            "online",
            "on the web",
            "senaste nyheterna",
            "aktuella nyheter",
            "senaste ai-nyheterna",
            "senaste ai nyheterna",
            "sök på webben",
            "sök efter",
            "leta upp",
            "på webben",
            "vad händer",
        )
    )

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
    if any(
        keyword in lowered
        for keyword in ("arkitektur", "systemdesign", "flerfils", "skriv om")
    ):
        complexity_score += 2
    if any(keyword in lowered for keyword in ("tests", "refactor", "backend")):
        complexity_score += 1
    if any(keyword in lowered for keyword in ("tester", "refaktorera", "backend")):
        complexity_score += 1
    if any(keyword in lowered for keyword in ("game", "tetris", "app", "website", "ui")):
        complexity_score += 2
    if any(
        keyword in lowered
        for keyword in ("spel", "tetrisspel", "app", "webbplats", "gränssnitt")
    ):
        complexity_score += 2
    if any(keyword in lowered for keyword in ("create", "build", "implement", "generate")):
        complexity_score += 1
    if any(keyword in lowered for keyword in ("skapa", "bygg", "implementera", "generera")):
        complexity_score += 1

    if any(
        keyword in lowered
        for keyword in ("explain", "summarize", "what does", "förklara", "sammanfatta", "vad gör")
    ):
        task_type = "explain"
    elif any(keyword in lowered for keyword in ("game", "tetris", "spel", "tetrisspel")):
        task_type = "large_refactor" if complexity_score >= 3 else "single_file_edit"
    elif any(
        keyword in lowered
        for keyword in ("create", "build", "implement", "generate", "skapa", "bygg", "implementera", "generera")
    ) and any(
        keyword in lowered
        for keyword in ("app", "website", "script", "program", "tool", "webbplats", "skript", "program", "verktyg")
    ):
        task_type = "large_refactor" if complexity_score >= 3 else "single_file_edit"
    elif any(keyword in lowered for keyword in ("test", "pytest", "unit test", "tester", "enhetstest")):
        task_type = "test_help" if complexity_score <= 3 else "multi_file_edit"
    elif any(keyword in lowered for keyword in ("refactor", "backend", "module", "refaktorera", "modul")):
        task_type = "large_refactor" if complexity_score >= 4 else "single_file_edit"
    elif any(keyword in lowered for keyword in ("fix", "bug", "error", "fel", "bugg")):
        task_type = "small_fix" if complexity_score <= 3 else "multi_file_edit"
    elif any(keyword in lowered for keyword in ("design", "architecture", "system", "arkitektur", "systemdesign")):
        task_type = "architecture"
    else:
        task_type = "unknown"

    return Classification(
        task_type=task_type,
        complexity_score=min(complexity_score, 5),
        token_estimate=token_estimate,
        requires_web=requires_web,
    )
