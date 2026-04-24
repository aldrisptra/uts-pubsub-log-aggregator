import importlib
import os
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    os.environ["DB_PATH"] = str(tmp_path / "events.db")

    import src.main as main

    importlib.reload(main)

    with TestClient(main.app) as test_client:
        yield test_client


def make_event(event_id: str = "evt-001", topic: str = "app.test"):
    return {
        "topic": topic,
        "event_id": event_id,
        "timestamp": "2026-04-24T10:00:00Z",
        "source": "pytest",
        "payload": {"message": "hello"},
    }


def wait_for_queue():
    time.sleep(0.3)


def test_publish_duplicate_event_dropped(client):
    event = make_event(event_id="dup-001")

    response1 = client.post("/publish", json=event)
    response2 = client.post("/publish", json=event)

    wait_for_queue()

    stats = client.get("/stats").json()

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert stats["received"] == 2
    assert stats["unique_processed"] == 1
    assert stats["duplicate_dropped"] == 1


def test_publish_batch_with_duplicates(client):
    batch = [
        make_event(event_id="batch-001", topic="app.batch"),
        make_event(event_id="batch-002", topic="app.batch"),
        make_event(event_id="batch-001", topic="app.batch"),
    ]

    response = client.post("/publish", json=batch)

    wait_for_queue()

    stats = client.get("/stats").json()
    events = client.get("/events?topic=app.batch").json()["events"]

    assert response.status_code == 200
    assert response.json()["accepted"] == 3
    assert stats["received"] == 3
    assert stats["unique_processed"] == 2
    assert stats["duplicate_dropped"] == 1
    assert len(events) == 2


def test_invalid_event_missing_topic(client):
    event = make_event()
    event.pop("topic")

    response = client.post("/publish", json=event)

    assert response.status_code == 422


def test_invalid_event_timestamp(client):
    event = make_event()
    event["timestamp"] = "not-a-timestamp"

    response = client.post("/publish", json=event)

    assert response.status_code == 422


def test_stats_and_events_consistent(client):
    client.post("/publish", json=make_event(event_id="s1", topic="app.stats"))
    client.post("/publish", json=make_event(event_id="s2", topic="app.stats"))

    wait_for_queue()

    stats = client.get("/stats").json()
    events = client.get("/events?topic=app.stats").json()["events"]

    assert stats["unique_processed"] == 2
    assert stats["topics"]["app.stats"] == 2
    assert len(events) == 2


def test_stress_5000_events_with_20_percent_duplicates(client):
    unique_count = 4000
    duplicate_count = 1000

    events = [
        make_event(event_id=f"stress-{i}", topic="app.stress")
        for i in range(unique_count)
    ]

    duplicates = [
        make_event(event_id=f"stress-{i}", topic="app.stress")
        for i in range(duplicate_count)
    ]

    batch = events + duplicates

    start = time.time()
    response = client.post("/publish", json=batch)

    wait_for_queue()

    elapsed = time.time() - start
    stats = client.get("/stats").json()

    assert response.status_code == 200
    assert response.json()["accepted"] == 5000
    assert stats["received"] == 5000
    assert stats["unique_processed"] == 4000
    assert stats["duplicate_dropped"] == 1000
    assert elapsed < 10