from codex_adv.config import DEFAULT_CONFIG
from codex_adv.self_heal import CrashContext, SelfHealingManager


def test_self_heal_records_incident_and_attempts_restart(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manager = SelfHealingManager(DEFAULT_CONFIG)
    restarted = False

    def fake_run_recovery(path):
        return "Applied a minimal recovery fix."

    def fake_restart():
        nonlocal restarted
        restarted = True

    manager._run_recovery = fake_run_recovery  # type: ignore[method-assign]
    manager._restart_process = fake_restart  # type: ignore[method-assign]

    recovered = manager.attempt_recovery(
        RuntimeError("boom"),
        CrashContext(command="chat", workdir=str(tmp_path), session_id="s1", last_prompt="hello"),
    )

    incident_files = list((tmp_path / ".codex-adv" / "incidents").glob("*.json"))
    assert recovered is True
    assert restarted is True
    assert len(incident_files) == 1
    assert "recovery_summary" in incident_files[0].read_text()


def test_self_heal_stops_if_recovery_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manager = SelfHealingManager(DEFAULT_CONFIG)
    manager._run_recovery = lambda path: ""  # type: ignore[method-assign]
    manager._restart_process = lambda: (_ for _ in ()).throw(AssertionError("should not restart"))  # type: ignore[method-assign]

    recovered = manager.attempt_recovery(
        RuntimeError("boom"),
        CrashContext(command="run", workdir=str(tmp_path)),
    )

    assert recovered is False
