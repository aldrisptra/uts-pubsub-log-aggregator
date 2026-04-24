import time


class RuntimeStats:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.received = 0
        self.duplicate_dropped = 0

    def increment_received(self, amount: int = 1) -> None:
        self.received += amount

    def increment_duplicate(self, amount: int = 1) -> None:
        self.duplicate_dropped += amount

    def uptime(self) -> float:
        return round(time.time() - self.started_at, 2)