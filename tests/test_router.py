from codex_adv.config import DEFAULT_CONFIG
from codex_adv.executor import ExecutionResult
from codex_adv.learning import LearningStore
from codex_adv.router import Router


def test_system_inspection_falls_back_to_cloud_when_local_does_not_use_tools(tmp_path):
    store = LearningStore(tmp_path / "memory.db")
    router = Router(DEFAULT_CONFIG, store)
    calls: list[tuple[str, str]] = []

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
        "go through my local machine and let me know "
        "if it's possible to optimize it for memory consumption"
    )

    assert response.initial_model == "local_heavy"
    assert response.final_model == "cloud"
    assert response.fallback_used is True
    assert response.success is True
    assert calls == [
        ("local_heavy", DEFAULT_CONFIG.profiles.local_heavy),
        ("cloud", DEFAULT_CONFIG.profiles.cloud),
    ]
