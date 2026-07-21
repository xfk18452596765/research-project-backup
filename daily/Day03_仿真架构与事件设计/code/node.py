"""Node model for the RL-PRMAC simulator."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from packet import Packet, PacketStatus


class MacState(str, Enum):
    """MAC protocol state of a node."""

    IDLE = "IDLE"
    BACKING_OFF = "BACKING_OFF"
    WAIT_CTS = "WAIT_CTS"
    TRANSMITTING = "TRANSMITTING"
    WAIT_ACK = "WAIT_ACK"
    RECEIVING = "RECEIVING"
    RESERVING = "RESERVING"
    WAIT_RESERVATION_ACK = "WAIT_RESERVATION_ACK"


@dataclass
class Node:
    """Basic node model shared by DCF, Fixed-PRMAC and RL-PRMAC."""

    node_id: int
    queue_limit: int = 100
    mac_state: MacState = MacState.IDLE
    tx_queue: deque[Packet] = field(default_factory=deque)
    neighbors: set[int] = field(default_factory=set)

    def enqueue(self, packet: Packet) -> bool:
        """Add a packet to the transmission queue.

        Returns:
            True if the packet is queued successfully.
            False if the queue is full.
        """
        if len(self.tx_queue) >= self.queue_limit:
            packet.status = PacketStatus.DROPPED
            return False

        packet.status = PacketStatus.QUEUED
        self.tx_queue.append(packet)
        return True

    def peek(self) -> Packet | None:
        """Return the head-of-line packet without removing it."""
        return self.tx_queue[0] if self.tx_queue else None

    def dequeue(self) -> Packet | None:
        """Remove and return the head-of-line packet."""
        return self.tx_queue.popleft() if self.tx_queue else None

    def clear_queue(self) -> None:
        """Remove all packets from the transmission queue."""
        self.tx_queue.clear()

    @property
    def queue_length(self) -> int:
        """Return the number of packets currently waiting."""
        return len(self.tx_queue)

    @property
    def queue_is_empty(self) -> bool:
        """Return True when the transmission queue is empty."""
        return not self.tx_queue

    @property
    def queue_is_full(self) -> bool:
        """Return True when the transmission queue reaches its limit."""
        return len(self.tx_queue) >= self.queue_limit
