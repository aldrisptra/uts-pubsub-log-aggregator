import os
import time
from datetime import datetime, timezone

import httpx


AGGREGATOR_URL = os.getenv("AGGREGATOR_URL", "http://localhost:8080")
TOTAL_EVENTS = int(os.getenv("TOTAL_EVENTS", "5000"))
DUPLICATE_RATIO = float(os.getenv("DUPLICATE_RATIO", "0.2"))


def make_event(event_id: str):
    return {
        "topic": "app.compose",
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "publisher-simulator",
        "payload": {
            "message": "event from publisher simulator"
        },
    }


def main():
    unique_count = int(TOTAL_EVENTS * (1 - DUPLICATE_RATIO))
    duplicate_count = TOTAL_EVENTS - unique_count

    events = [make_event(f"compose-{i}") for i in range(unique_count)]
    duplicates = [make_event(f"compose-{i}") for i in range(duplicate_count)]

    batch = events + duplicates

    print(f"Waiting for aggregator at {AGGREGATOR_URL}...")
    time.sleep(3)

    print(f"Sending {len(batch)} events...")
    response = httpx.post(f"{AGGREGATOR_URL}/publish", json=batch, timeout=30)
    print(response.status_code)
    print(response.json())

    stats = httpx.get(f"{AGGREGATOR_URL}/stats", timeout=30)
    print(stats.json())


if __name__ == "__main__":
    main()