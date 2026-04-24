from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Event(BaseModel):
    topic: str = Field(..., min_length=1)
    event_id: str = Field(..., min_length=1)
    timestamp: datetime
    source: str = Field(..., min_length=1)
    payload: dict[str, Any]


class PublishResponse(BaseModel):
    accepted: int


class StatsResponse(BaseModel):
    received: int
    unique_processed: int
    duplicate_dropped: int
    topics: dict[str, int]
    uptime: float