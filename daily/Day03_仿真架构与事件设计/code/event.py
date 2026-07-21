"""Simulation event definition."""
from __future__ import annotations
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable

_sequence = count()

@dataclass(order=True, slots=True)
class Event:
    time: float
    priority: int
    sequence: int = field(default_factory=lambda: next(_sequence))
    callback: Callable[..., Any] = field(compare=False, default=lambda: None)
    event_type: str = field(compare=False, default="GENERIC")
    args: tuple[Any, ...] = field(compare=False, default_factory=tuple)
    kwargs: dict[str, Any] = field(compare=False, default_factory=dict)

    def execute(self) -> Any:
        return self.callback(*self.args, **self.kwargs)
