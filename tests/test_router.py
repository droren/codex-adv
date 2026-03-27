from codex_adv.config import DEFAULT_CONFIG
from codex_adv.executor import ExecutionResult
from codex_adv.intent import IntentPlan
from codex_adv.learning import LearningStore
from codex_adv.router import Router


def test_broad_system_inspection_returns_clarification_instead_of_running(tmp_path):
    store = LearningStore(tmp_path / "memory.db")
    router = Router(DEFAULT_CONFIG, store)
    called = False

    def fake_execute(prompt, route, profile, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("router should not execute for broad prompts")

    router._execute = fake_execute  # type: ignore[method-assign]
    router._clarification_plan_for = lambda prompt, classification: IntentPlan(  # type: ignore[method-assign]
        normalized_intent=(
            "Inspect this machine for likely memory-consumption causes "
            "and suggest concrete optimization actions."
        ),
        needs_clarification=True,
        reason="The request is still broad after normalization.",
        options=(
            "Inspect memory pressure, swap, and top RAM-consuming processes first.",
            "Inspect background services and always-on software.",
            "Inspect developer workloads such as Docker, browsers, and local AI models.",
        ),
    )

    response = router.run(
        "go through my local machine and let me know "
        "if it's possible to optimize it for memory consumption",
        app_session_id="session-1",
    )

    assert response.final_model == "router"
    assert response.rewrite_strategy == "clarify"
    assert "Normalized intent" in response.output
    assert "1." in response.output
    assert called is False


def test_system_inspection_falls_back_to_cloud_when_local_does_not_use_tools(tmp_path):
    store = LearningStore(tmp_path / "memory.db")
    router = Router(DEFAULT_CONFIG, store)
    calls: list[tuple[str, str]] = []
    router._clarification_plan_for = lambda prompt, classification: None  # type: ignore[method-assign]

    def fake_execute(prompt, route, profile, **kwargs):
        calls.append((route, profile))
        if route == "local_heavy":
            return ExecutionResult(
                profile=profile,
                command=["codex"],
                stdout="I'll run this command now and inspect the machine.",
                raw_output='{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5,"cached_input_tokens":0}}',
                stderr="",
                exit_code=0,
                latency_seconds=1.0,
                session_id=None,
                input_tokens=10,
                output_tokens=5,
                cached_input_tokens=0,
                interrupted=False,
            )
        return ExecutionResult(
            profile=profile,
            command=["codex"],
            stdout="I checked memory pressure, top consumers, and swap usage.",
            raw_output='{"type":"item.completed","item":{"type":"command_execution","command":"vm_stat"}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":20,"output_tokens":15,"cached_input_tokens":0}}',
            stderr="",
            exit_code=0,
            latency_seconds=2.0,
            session_id=None,
            input_tokens=20,
            output_tokens=15,
            cached_input_tokens=0,
            interrupted=False,
        )

    router._execute = fake_execute  # type: ignore[method-assign]

    response = router.run(
        "inspect memory pressure, swap usage, and top RAM-consuming processes "
        "on this machine"
    )

    assert response.initial_model == "local_heavy"
    assert response.final_model == "cloud"
    assert response.fallback_used is True
    assert response.success is True
    assert calls == [
        ("local_heavy", DEFAULT_CONFIG.profiles.local_heavy),
        ("cloud", DEFAULT_CONFIG.profiles.cloud),
    ]
