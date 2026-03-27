from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from codex_adv.classifier import Classification, classify_prompt
from codex_adv.config import AppConfig
from codex_adv.executor import (
    ExecutionResult,
    ExecutorSettings,
    resume_codex,
    run_codex,
    stream_codex,
    stream_resume_codex,
)
from codex_adv.intent import IntentPlan, analyze_intent, should_analyze_intent
from codex_adv.learning import LearningStore, RequestRecord
from codex_adv.rewriters import RewriteResult, rewrite_for_cloud, rewrite_for_local


@dataclass(slots=True)
class RoutedResponse:
    output: str
    raw_output: str
    classification: Classification
    initial_model: str
    final_model: str
    fallback_used: bool
    success: bool
    failure_reason: str
    rewritten_prompt: str
    rewrite_strategy: str
    latency_seconds: float


class Router:
    def __init__(self, config: AppConfig, store: LearningStore) -> None:
        self.config = config
        self.store = store

    def run(
        self,
        prompt: str,
        conversation: list[object] | None = None,
        stream_handler: Callable[[str], None] | None = None,
        app_session_id: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> RoutedResponse:
        classification = classify_prompt(prompt)
        clarification_plan = self._clarification_plan_for(prompt, classification)
        if clarification_plan is not None:
            return self._clarification_response(
                prompt,
                classification,
                clarification_plan=clarification_plan,
                app_session_id=app_session_id or "",
            )
        initial_model = self._choose_model(classification)
        routed_prompt = self._with_conversation_context(prompt, conversation)

        if initial_model in {"local_fast", "local_heavy"}:
            rewrite = rewrite_for_local(
                routed_prompt, classification, self.config.rewrites.local.style
            )
            first_result = self._execute(
                rewrite.rewritten_prompt,
                initial_model,
                self._profile_for_route(initial_model),
                app_session_id=app_session_id,
                stream_handler=stream_handler,
                cancel_event=cancel_event,
            )
        else:
            rewrite = rewrite_for_cloud(
                routed_prompt, classification, self.config.rewrites.cloud.style
            )
            first_result = self._execute(
                rewrite.rewritten_prompt,
                "cloud",
                self.config.profiles.cloud,
                app_session_id=app_session_id,
                stream_handler=stream_handler,
                cancel_event=cancel_event,
            )

        first_success, first_failure_reason = self._assess(
            first_result, classification
        )
        final_result = first_result
        final_model = initial_model
        fallback_used = False
        final_rewrite = rewrite

        if (
            not first_success
            and initial_model in {"local_fast", "local_heavy"}
            and self.config.fallback.enabled
            and self.config.fallback.max_attempts > 1
            and not first_result.interrupted
        ):
            fallback_used = True
            final_model = "cloud"
            if stream_handler is not None:
                stream_handler(
                    "\n[router] local response looked weak, retrying with cloud...\n\n"
                )
            final_rewrite = rewrite_for_cloud(
                routed_prompt, classification, self.config.rewrites.cloud.style
            )
            final_result = self._execute(
                final_rewrite.rewritten_prompt,
                "cloud",
                self.config.profiles.cloud,
                app_session_id=app_session_id,
                stream_handler=stream_handler,
                cancel_event=cancel_event,
            )

        success, failure_reason = self._assess(final_result, classification)
        self._log(
            session_id=app_session_id or "",
            prompt=prompt,
            classification=classification,
            model=final_model,
            rewrite=final_rewrite,
            fallback_used=fallback_used,
            success=success,
            failure_reason=failure_reason if success is False else first_failure_reason,
            latency=final_result.latency_seconds,
            actual_tokens_used=final_result.input_tokens + final_result.output_tokens,
            input_tokens=final_result.input_tokens,
            output_tokens=final_result.output_tokens,
            cached_input_tokens=final_result.cached_input_tokens,
        )

        combined_output = final_result.stdout.strip() or final_result.stderr.strip()
        return RoutedResponse(
            output=combined_output,
            raw_output=final_result.raw_output,
            classification=classification,
            initial_model=initial_model,
            final_model=final_model,
            fallback_used=fallback_used,
            success=success,
            failure_reason=failure_reason,
            rewritten_prompt=final_rewrite.rewritten_prompt,
            rewrite_strategy=final_rewrite.strategy,
            latency_seconds=final_result.latency_seconds,
        )

    def _clarification_response(
        self,
        prompt: str,
        classification: Classification,
        *,
        clarification_plan: IntentPlan,
        app_session_id: str,
    ) -> RoutedResponse:
        options = "\n".join(
            f"{index}. {option}"
            for index, option in enumerate(
                clarification_plan.options[:3],
                start=1,
            )
        )
        output = (
            "I can investigate this, but the request is still broad after normalization.\n\n"
            f"Normalized intent:\n{clarification_plan.normalized_intent}\n\n"
            "Pick one direction so I don't optimize the wrong thing:\n"
            f"{options}\n\n"
            "Reply with 1, 2, or 3, or rewrite the request with the focus you want."
        )
        self._log(
            session_id=app_session_id,
            prompt=prompt,
            classification=classification,
            model="router",
            rewrite=RewriteResult(
                rewritten_prompt=clarification_plan.normalized_intent,
                strategy="clarify",
            ),
            fallback_used=False,
            success=True,
            failure_reason=clarification_plan.reason or "needs_clarification",
            latency=0.0,
            actual_tokens_used=0,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
        )
        return RoutedResponse(
            output=output,
            raw_output="",
            classification=classification,
            initial_model="router",
            final_model="router",
            fallback_used=False,
            success=True,
            failure_reason="needs_clarification",
            rewritten_prompt=clarification_plan.normalized_intent,
            rewrite_strategy="clarify",
            latency_seconds=0.0,
        )

    def _clarification_plan_for(
        self,
        prompt: str,
        classification: Classification,
    ) -> IntentPlan | None:
        if not should_analyze_intent(prompt, classification):
            return None
        plan = analyze_intent(
            prompt,
            classification,
            profile=self.config.profiles.local_fast,
        )
        if plan is None or not plan.needs_clarification or not plan.options:
            return None
        return plan

    def _execute(
        self,
        prompt: str,
        route: str,
        profile: str,
        *,
        app_session_id: str | None = None,
        stream_handler: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ExecutionResult:
        if not self.config.execution.reuse_codex_sessions:
            return (
                stream_codex(
                    prompt,
                    profile,
                    on_chunk=stream_handler,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
                if stream_handler is not None
                else run_codex(
                    prompt,
                    profile,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
            )

        existing_session_id = (
            self.store.get_exec_session_id(app_session_id, route)
            if app_session_id is not None
            else None
        )

        if stream_handler is not None:
            result = (
                stream_resume_codex(
                    prompt,
                    existing_session_id,
                    on_chunk=stream_handler,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
                if existing_session_id
                else stream_codex(
                    prompt,
                    profile,
                    on_chunk=stream_handler,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
            )
        else:
            result = (
                resume_codex(
                    prompt,
                    existing_session_id,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
                if existing_session_id
                else run_codex(
                    prompt,
                    profile,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
            )

        if existing_session_id and result.exit_code != 0 and not result.interrupted:
            if app_session_id is not None:
                self.store.clear_exec_session_id(app_session_id, route)
            result = (
                stream_codex(
                    prompt,
                    profile,
                    on_chunk=stream_handler,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
                if stream_handler is not None
                else run_codex(
                    prompt,
                    profile,
                    settings=self._executor_settings(),
                    cancel_event=cancel_event,
                )
            )

        if app_session_id is not None and result.session_id:
            self.store.set_exec_session_id(app_session_id, route, result.session_id)
        return result

    def _choose_model(self, classification: Classification) -> str:
        task_type = classification.task_type
        if classification.requires_web:
            return "cloud"
        if task_type == "system_inspection":
            return "local_heavy"
        if task_type in {"unknown", "explain"}:
            return "local_fast"
        if task_type in self.config.routing.prefer_local_task_types:
            return "local_fast"
        if task_type in {"multi_file_edit", "architecture", "large_refactor"}:
            return "local_heavy"

        historical_success = self.store.success_rate("local_heavy", task_type)
        if historical_success is not None:
            return (
                "local_heavy"
                if historical_success >= self.config.routing.min_local_success_rate
                else "cloud"
            )

        if (
            classification.complexity_score > self.config.routing.simple_complexity_threshold
            and task_type in self.config.routing.cloud_task_types
        ):
            return "cloud"
        return "local_fast"

    def _assess(
        self, result: ExecutionResult, classification: Classification
    ) -> tuple[bool, str]:
        if result.exit_code != 0:
            if result.interrupted:
                return False, "interrupted"
            return False, f"codex exited with {result.exit_code}"

        if classification.task_type == "system_inspection" and not self._has_tool_activity(result):
            return False, "missing_tool_activity"

        output = result.stdout.strip()
        min_output_chars = self._min_output_chars(classification)
        if len(output) < min_output_chars:
            return False, "output_too_short"

        if self._looks_like_fake_execution(output) and not self._has_tool_activity(result):
            return False, "missing_tool_activity"

        for marker in self.config.fallback.failure_markers:
            if marker.lower() in output.lower():
                return False, f"failure_marker:{marker}"

        return True, ""

    def _min_output_chars(self, classification: Classification) -> int:
        if classification.task_type in {"unknown", "explain"}:
            return 1
        if classification.task_type == "system_inspection":
            return min(20, self.config.fallback.min_output_chars)
        if classification.task_type in {"small_fix", "test_help"}:
            return min(20, self.config.fallback.min_output_chars)
        return self.config.fallback.min_output_chars

    def _has_tool_activity(self, result: ExecutionResult) -> bool:
        markers = (
            '"type":"command_execution"',
            '"name":"exec_command"',
            "/bin/zsh -lc",
            '"type":"web_search"',
        )
        return any(marker in result.raw_output for marker in markers)

    def _looks_like_fake_execution(self, output: str) -> bool:
        lowered = output.lower()
        suspicious_phrases = (
            "let's try this again",
            "it seems there was an issue",
            "i'll run this command",
            "will execute this now",
            "i will execute this now",
            "let me know if you have any other requests while i retrieve this information",
        )
        return any(phrase in lowered for phrase in suspicious_phrases)

    def _profile_for_route(self, route: str) -> str:
        if route == "local_fast":
            return self.config.profiles.local_fast
        if route == "local_heavy":
            return self.config.profiles.local_heavy
        if route == "cloud":
            return self.config.profiles.cloud
        raise ValueError(f"Unknown route: {route}")

    def _executor_settings(self) -> ExecutorSettings:
        return ExecutorSettings(
            web_search=self.config.execution.web_search,
            dangerous_bypass_approvals_and_sandbox=(
                self.config.execution.dangerous_bypass_approvals_and_sandbox
            ),
            ephemeral_codex_sessions=self.config.execution.ephemeral_codex_sessions,
        )

    def _log(
        self,
        *,
        session_id: str,
        prompt: str,
        classification: Classification,
        model: str,
        rewrite: RewriteResult,
        fallback_used: bool,
        success: bool,
        failure_reason: str,
        latency: float,
        actual_tokens_used: int,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int,
    ) -> None:
        self.store.log_request(
            RequestRecord(
                session_id=session_id,
                timestamp=datetime.now(UTC).isoformat(),
                prompt=prompt,
                rewritten_prompt=rewrite.rewritten_prompt,
                task_type=classification.task_type,
                complexity_score=classification.complexity_score,
                chosen_model=model,
                fallback_used=fallback_used,
                success=success,
                latency=latency,
                token_estimate=classification.token_estimate,
                actual_tokens_used=actual_tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                rewrite_strategy=rewrite.strategy,
                failure_reason=failure_reason,
            )
        )


    def _with_conversation_context(
        self, prompt: str, conversation: list[object] | None
    ) -> str:
        if not conversation:
            return prompt

        recent_messages = conversation[-6:]
        formatted_messages: list[str] = []
        for message in recent_messages:
            role = self._message_field(message, "role")
            content = self._message_field(message, "content")
            if not role or not content:
                continue
            formatted_messages.append(f"{role}: {content}")

        if not formatted_messages:
            return prompt

        context = "\n".join(formatted_messages)
        return (
            "Conversation context:\n"
            f"{context}\n\n"
            "Current user request:\n"
            f"{prompt}"
        )

    def _message_field(self, message: object, field: str) -> str:
        if isinstance(message, dict):
            value = message.get(field, "")
            return str(value)
        try:
            value = message[field]  # type: ignore[index]
            return str(value)
        except (KeyError, IndexError, TypeError):
            return str(getattr(message, field, ""))
        return str(getattr(message, field, ""))
