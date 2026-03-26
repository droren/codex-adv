from codex_adv.learning import LearningStore, MessageRecord


def test_delete_last_message_removes_latest_entry(tmp_path):
    store = LearningStore(tmp_path / "memory.db")
    session = store.create_session(
        title="Interrupt session",
        timestamp="2026-03-26T00:00:00+00:00",
    )
    store.add_message(
        MessageRecord(
            session_id=session.id,
            timestamp="2026-03-26T00:00:01+00:00",
            role="user",
            content="first",
        )
    )
    store.add_message(
        MessageRecord(
            session_id=session.id,
            timestamp="2026-03-26T00:00:02+00:00",
            role="user",
            content="second",
        )
    )

    store.delete_last_message(session.id)

    rows = store.get_messages(session.id)
    assert len(rows) == 1
    assert rows[0]["content"] == "first"
