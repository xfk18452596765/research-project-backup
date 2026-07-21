"""Abstract shared wireless channel."""
from dataclasses import dataclass
from enum import Enum

class ChannelState(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    COLLISION = "COLLISION"

@dataclass
class Channel:
    state: ChannelState = ChannelState.IDLE
    owner: int | None = None
    busy_until: float = 0.0

    def is_idle(self, now: float) -> bool:
        if self.state == ChannelState.BUSY and now >= self.busy_until:
            self.release()
        return self.state == ChannelState.IDLE

    def occupy(self, node_id: int, now: float, duration: float) -> None:
        if duration <= 0:
            raise ValueError("Duration must be positive.")
        if not self.is_idle(now):
            raise RuntimeError("Channel is busy.")
        self.state = ChannelState.BUSY
        self.owner = node_id
        self.busy_until = now + duration

    def release(self) -> None:
        self.state = ChannelState.IDLE
        self.owner = None
        self.busy_until = 0.0
