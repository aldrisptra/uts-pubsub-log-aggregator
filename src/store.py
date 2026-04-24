import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DedupStore:
    def __init__(self, db_path: str = "data/events.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    topic TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (topic, event_id)
                )
                """
            )

    def save_event(self, event: dict[str, Any]) -> bool:
        """
        Return True jika event baru berhasil diproses.
        Return False jika event duplicate.
        """
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO processed_events (
                        topic, event_id, timestamp, source, payload, processed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["topic"],
                        event["event_id"],
                        str(event["timestamp"]),
                        event["source"],
                        json.dumps(event["payload"]),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_events(self, topic: str | None = None) -> list[dict[str, Any]]:
        if topic:
            rows = self.conn.execute(
                """
                SELECT topic, event_id, timestamp, source, payload, processed_at
                FROM processed_events
                WHERE topic = ?
                ORDER BY processed_at ASC
                """,
                (topic,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT topic, event_id, timestamp, source, payload, processed_at
                FROM processed_events
                ORDER BY processed_at ASC
                """
            ).fetchall()

        return [
            {
                "topic": row["topic"],
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "source": row["source"],
                "payload": json.loads(row["payload"]),
                "processed_at": row["processed_at"],
            }
            for row in rows
        ]

    def count_unique(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS total FROM processed_events"
        ).fetchone()
        return int(row["total"])

    def count_topics(self) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT topic, COUNT(*) AS total
            FROM processed_events
            GROUP BY topic
            """
        ).fetchall()

        return {row["topic"]: int(row["total"]) for row in rows}

    def close(self) -> None:
        self.conn.close()