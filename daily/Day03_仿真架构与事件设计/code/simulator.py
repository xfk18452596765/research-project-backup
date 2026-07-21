"""Single-threaded priority-queue discrete-event simulator."""
from __future__ import annotations
import heapq
from dataclasses import dataclass, field
from typing import Any, Callable
from event import Event

@dataclass
class Simulator:
    now: float = 0.0
    events_processed: int = 0
    log_enabled: bool = True
    _queue: list[Event] = field(default_factory=list)
    log_records: list[str] = field(default_factory=list)

    def schedule(self, delay: float, callback: Callable[..., Any], *,
                 event_type: str = "GENERIC", priority: int = 50,
                 args: tuple[Any, ...] = (), kwargs: dict[str, Any] | None = None) -> Event:
        if delay < 0:
            raise ValueError("Event delay cannot be negative.")
        event = Event(self.now + delay, priority, callback=callback,
                      event_type=event_type, args=args, kwargs=kwargs or {})
        heapq.heappush(self._queue, event)
        return event

    def schedule_at(self, time: float, callback: Callable[..., Any], **options: Any) -> Event:
        if time < self.now:
            raise ValueError("Cannot schedule an event in the past.")
        return self.schedule(time - self.now, callback, **options)

    def run(self, *, until: float | None = None, max_events: int | None = None) -> None:
        while self._queue:
            if max_events is not None and self.events_processed >= max_events:
                break
            event = heapq.heappop(self._queue)
            if until is not None and event.time > until:
                heapq.heappush(self._queue, event)
                self.now = until
                break
            self.now = event.time
            self.events_processed += 1
            message = f"[t={self.now:.6f}] {event.event_type} (priority={event.priority})"
            if self.log_enabled:
                self.log_records.append(message)
                print(message)
            event.execute()

    def has_pending_events(self) -> bool:
        return bool(self._queue)
