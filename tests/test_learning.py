from codex_adv.learning import LearningStore, RequestRecord


def test_learning_store_summary(tmp_path):
    store = LearningStore(tmp_path / "memory.db")
    store.log_request(
        RequestRecord(
            timestamp="2026-03-24T00:00:00+00:00",
            prompt="Fix bug",
            rewritten_prompt="Fix bug",
            task_type="small_fix",
            complexity_score=2,
            chosen_model="local",
            fallback_used=False,
            success=True,
            latency=0.5,
            token_estimate=10,
            rewrite_strategy="compress",
        )
    )

    assert store.success_rate("local", "small_fix") == 1.0
    rows = store.summary()
    assert len(rows) == 1


def test_learning_store_backfills_legacy_usage_columns(tmp_path):
    store = LearningStore(tmp_path / "memory.db")
    store.log_request(
        RequestRecord(
            timestamp="2026-03-24T00:00:00+00:00",
            prompt="Legacy request",
            rewritten_prompt="Legacy request",
            task_type="unknown",
            complexity_score=1,
            chosen_model="local_fast",
            fallback_used=False,
            success=True,
            latency=1.2,
            token_estimate=10,
            rewrite_strategy="compress",
            actual_tokens_used=321,
        )
    )

    reloaded = LearningStore(tmp_path / "memory.db")
    totals = reloaded.session_usage_totals("")

    assert totals["actual_tokens_used"] == 321
    assert totals["input_tokens"] == 321
    assert totals["output_tokens"] == 0
