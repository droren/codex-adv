from __future__ import annotations

import json
from dataclasses import dataclass

from codex_adv.classifier import Classification
from codex_adv.executor import ExecutorSettings, run_codex

INTENT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "normalized_intent": {"type": "string"},
        "needs_clarification": {"type": "boolean"},
        "reason": {"type": "string"},
        "options": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string"},
        },
    },
    "required": ["normalized_intent", "needs_clarification", "reason", "options"],
}


@dataclass(slots=True)
class IntentPlan:
    normalized_intent: str
    needs_clarification: bool
    reason: str
    options: tuple[str, ...]


def should_analyze_intent(prompt: str, classification: Classification) -> bool:
    lowered = prompt.lower()
    broad_markers = (
        "go through",
        "look through",
        "review my",
        "optimize",
        "improve",
        "help me with",
        "analyze my",
        "gå igenom",
        "se över",
        "optimera",
        "förbättra",
        "hjälp mig med",
    )
    narrow_markers = (
        "fix",
        "patch",
        "implement",
        "create",
        "build",
        "inspect memory pressure",
        "inspect swap",
        "search the web",
        "latest news",
        "sök på webben",
        "senaste nyheterna",
    )
    if classification.requires_web:
        return False
    if any(marker in lowered for marker in narrow_markers):
        return False
    if any(marker in lowered for marker in broad_markers):
        return True
    return (
        classification.task_type in {"system_inspection"}
        and classification.complexity_score <= 3
    )


def analyze_intent(
    prompt: str,
    classification: Classification,
    *,
    profile: str,
) -> IntentPlan | None:
    instructions = (
        "Analyze the user request and normalize it.\n"
        "Decide whether it is still too broad to execute safely without choosing a direction.\n"
        "If it is broad, provide at most 3 distinct execution angles.\n"
        "Prefer proceeding without clarification when the request is already concrete enough.\n\n"
        f"Task type: {classification.task_type}\n"
        f"Complexity: {classification.complexity_score}/5\n"
        f"Original request:\n{prompt}\n"
    )
    result = run_codex(
        instructions,
        profile,
        settings=ExecutorSettings(),
        output_schema=INTENT_SCHEMA,
    )
    if result.exit_code != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    normalized_intent = str(payload.get("normalized_intent", "")).strip()
    reason = str(payload.get("reason", "")).strip()
    options = payload.get("options", [])
    if not isinstance(options, list):
        options = []
    cleaned_options = tuple(str(option).strip() for option in options if str(option).strip())[:3]
    return IntentPlan(
        normalized_intent=normalized_intent or prompt.strip(),
        needs_clarification=bool(payload.get("needs_clarification", False)),
        reason=reason,
        options=cleaned_options,
    )
