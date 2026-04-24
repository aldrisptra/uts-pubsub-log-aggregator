from src.store import DedupStore


def make_event(event_id: str = "evt-001", topic: str = "app.test"):
    return {
        "topic": topic,
        "event_id": event_id,
        "timestamp": "2026-04-24T10:00:00Z",
        "source": "pytest",
        "payload": {"message": "hello"},
    }


def test_dedup_duplicate_event_processed_once(tmp_path):
    db_path = tmp_path / "events.db"
    store = DedupStore(str(db_path))

    event = make_event()

    assert store.save_event(event) is True
    assert store.save_event(event) is False
    assert store.count_unique() == 1

    store.close()


def test_dedup_persists_after_store_reopen(tmp_path):
    db_path = tmp_path / "events.db"

    store1 = DedupStore(str(db_path))
    event = make_event(event_id="persist-001")
    assert store1.save_event(event) is True
    store1.close()

    store2 = DedupStore(str(db_path))
    assert store2.save_event(event) is False
    assert store2.count_unique() == 1
    store2.close()


def test_get_events_by_topic(tmp_path):
    db_path = tmp_path / "events.db"
    store = DedupStore(str(db_path))

    store.save_event(make_event(event_id="a1", topic="app.login"))
    store.save_event(make_event(event_id="a2", topic="app.login"))
    store.save_event(make_event(event_id="b1", topic="app.payment"))

    login_events = store.get_events(topic="app.login")

    assert len(login_events) == 2
    assert all(event["topic"] == "app.login" for event in login_events)

    store.close()