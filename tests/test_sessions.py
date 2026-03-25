from codex_adv.learning import LearningStore, MessageRecord


def test_session_and_messages(tmp_path):
    store = LearningStore(tmp_path / "memory.db")
    session = store.create_session(
        title="Test session",
        timestamp="2026-03-25T00:00:00+00:00",
    )
    store.add_message(
        MessageRecord(
            session_id=session.id,
            timestamp="2026-03-25T00:00:01+00:00",
            role="user",
            content="hello",
        )
    )

    rows = store.get_messages(session.id)
    assert len(rows) == 1
    assert rows[0]["content"] == "hello"
    assert store.latest_session_id() == session.id
