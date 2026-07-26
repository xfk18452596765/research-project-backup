"""Day11-compatible Fixed-PRMAC frame and reservation-state models.

This module preserves the Day09 public fields and retains the REJECTED state and
``rejected_at`` timestamp required by the Day10 conflict model. Day09 files are
not modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PRMACFrameType(str, Enum):
    """Control and data frame types frozen by the RL-PRMAC design."""

    PR_REQ = "PR_REQ"
    PR_ACK = "PR_ACK"
    PR_NACK = "PR_NACK"
    RELEASE = "RELEASE"
    DATA = "DATA"
    H_ACK = "H_ACK"


class ReservationStatus(str, Enum):
    """Lifecycle state of one path-segment reservation."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"  # Retained only for backward compatibility.


@dataclass(frozen=True, slots=True)
class ReservedLink:
    """One directed link included in a reservation segment."""

    sender: int
    receiver: int

    def __post_init__(self) -> None:
        if self.sender < 0 or self.receiver < 0:
            raise ValueError("Link node identifiers cannot be negative.")
        if self.sender == self.receiver:
            raise ValueError("A reserved link must connect two distinct nodes.")


@dataclass(frozen=True, slots=True)
class PRMACFrame:
    """Abstract Fixed-PRMAC frame used by the event-level simulator."""

    frame_type: PRMACFrameType
    flow_id: str
    packet_id: int
    sender: int
    receiver: int
    path: tuple[int, ...]
    segment_start_index: int
    requested_hops: int
    effective_hops: int
    priority: int
    duration: float
    created_at: float
    reserved_links: tuple[ReservedLink, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.flow_id:
            raise ValueError("flow_id cannot be empty.")
        if self.packet_id < 0:
            raise ValueError("packet_id cannot be negative.")
        if self.sender < 0 or self.receiver < 0:
            raise ValueError("Frame node identifiers cannot be negative.")
        if self.sender == self.receiver:
            raise ValueError("A frame sender and receiver must differ.")
        if len(self.path) < 2:
            raise ValueError("A PRMAC frame requires a path with at least one hop.")
        if not 0 <= self.segment_start_index < len(self.path) - 1:
            raise ValueError("segment_start_index is outside the forwarding path.")
        if self.requested_hops <= 0:
            raise ValueError("requested_hops must be positive.")
        if not 1 <= self.effective_hops <= self.requested_hops:
            raise ValueError("effective_hops must be in [1, requested_hops].")
        if self.duration <= 0:
            raise ValueError("Reservation duration must be positive.")
        if self.created_at < 0:
            raise ValueError("created_at cannot be negative.")


@dataclass(slots=True)
class ReservationRecord:
    """State stored for one requested path-segment reservation."""

    reservation_id: str
    flow_id: str
    packet_id: int
    path: tuple[int, ...]
    segment_start_index: int
    requested_hops: int
    effective_hops: int
    reserved_links: tuple[ReservedLink, ...]
    initiator: int
    endpoint: int
    priority: int
    duration: float
    requested_at: float
    status: ReservationStatus = ReservationStatus.PENDING
    activated_at: float | None = None
    expires_at: float | None = None
    released_at: float | None = None
    rejected_at: float | None = None
    failure_reason: str = ""

    def __post_init__(self) -> None:
        if not self.reservation_id:
            raise ValueError("reservation_id cannot be empty.")
        if len(self.reserved_links) != self.effective_hops:
            raise ValueError("reserved_links length must equal effective_hops.")


@dataclass(frozen=True, slots=True)
class ReservationTraceRecord:
    """One observable control-plane transition."""

    time: float
    event: str
    node_id: int
    packet_id: int
    reservation_id: str
    frame_type: str = ""
    detail: str = ""
