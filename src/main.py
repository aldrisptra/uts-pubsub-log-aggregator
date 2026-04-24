import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query
from src.models import Event, PublishResponse, StatsResponse
from src.stats import RuntimeStats
from src.store import DedupStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

DB_PATH = os.getenv("DB_PATH", "data/events.db")

store = DedupStore(DB_PATH)
stats = RuntimeStats()
event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


async def consumer_worker() -> None:
    while True:
        event = await event_queue.get()

        is_new = store.save_event(event)

        if is_new:
            logging.info(
                "Processed event topic=%s event_id=%s",
                event["topic"],
                event["event_id"],
            )
        else:
            stats.increment_duplicate()
            logging.info(
                "Duplicate dropped topic=%s event_id=%s",
                event["topic"],
                event["event_id"],
            )

        event_queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(consumer_worker())
    yield
    task.cancel()
    store.close()


app = FastAPI(
    title="Pub-Sub Log Aggregator",
    description="Local Pub-Sub log aggregator with idempotent consumer and deduplication",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/publish", response_model=PublishResponse)
async def publish(events: Event | list[Event]) -> PublishResponse:
    if isinstance(events, Event):
        event_list = [events]
    else:
        event_list = events

    stats.increment_received(len(event_list))

    for event in event_list:
        await event_queue.put(event.model_dump())

    return PublishResponse(accepted=len(event_list))


@app.get("/events")
async def get_events(topic: str | None = Query(default=None)):
    return {
        "events": store.get_events(topic=topic)
    }


@app.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    return StatsResponse(
        received=stats.received,
        unique_processed=store.count_unique(),
        duplicate_dropped=stats.duplicate_dropped,
        topics=store.count_topics(),
        uptime=stats.uptime(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )