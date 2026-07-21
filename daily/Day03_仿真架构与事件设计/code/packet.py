"""Packet model shared by DCF, Fixed-PRMAC, and RL-PRMAC."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class PacketStatus(str, Enum):
    """Lifecycle state of a packet."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    CONTENDING = "CONTENDING"
    TRANSMITTING = "TRANSMITTING"
    FORWARDED = "FORWARDED"
    DELIVERED = "DELIVERED"
    DROPPED = "DROPPED"


@dataclass(slots=True)
class Packet:
    """Basic packet model for the discrete-event simulator."""

    packet_id: int
    source: int
    destination: int
    created_at: float
    size_bytes: int = 1024
    priority: int = 0
    route: Sequence[int] = field(default_factory=tuple)
    current_hop_index: int = 0
    retries: int = 0
    status: PacketStatus = PacketStatus.CREATED
    delivered_at: float | None = None

    def __post_init__(self) -> None:
        """Validate packet parameters after initialization."""
        if self.created_at < 0:
            raise ValueError("created_at cannot be negative.")

        if self.size_bytes <= 0:
            raise ValueError("size_bytes must be positive.")

        if self.current_hop_index < 0:
            raise ValueError("current_hop_index cannot be negative.")

        if self.route:
            if self.route[0] != self.source:
                raise ValueError("The first node in route must equal source.")
            if self.route[-1] != self.destination:
                raise ValueError("The last node in route must equal destination.")
            if self.current_hop_index >= len(self.route):
                raise ValueError("current_hop_index is outside the route.")

    @property
    def current_node(self) -> int:
        """Return the node currently holding the packet."""
        if self.route:
            return self.route[self.current_hop_index]
        return self.source

    @property
    def next_hop(self) -> int | None:
        """Return the next-hop node, or None at the destination."""
        if not self.route:
            return None

        next_index = self.current_hop_index + 1
        if next_index >= len(self.route):
            return None
        return self.route[next_index]

    @property
    def remaining_hops(self) -> int:
        """Return the number of hops remaining to the destination."""
        if not self.route:
            return 0
        return max(0, len(self.route) - 1 - self.current_hop_index)

    @property
    def end_to_end_delay(self) -> float | None:
        """Return end-to-end delay after successful delivery."""
        if self.delivered_at is None:
            return None
        return self.delivered_at - self.created_at

    def advance_hop(self) -> None:
        """Move the packet to the next node on its route."""
        if not self.route:
            raise RuntimeError("Cannot advance a packet without a route.")

        if self.current_hop_index >= len(self.route) - 1:
            raise RuntimeError("Packet is already at the destination.")

        self.current_hop_index += 1
        self.status = (
            PacketStatus.DELIVERED
            if self.current_hop_index == len(self.route) - 1
            else PacketStatus.FORWARDED
        )

    def increment_retry(self) -> None:
        """Increase the packet retry counter."""
        self.retries += 1
