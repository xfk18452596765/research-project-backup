"""Configuration for the Day04 minimum single-hop DCF model.

Time is represented in seconds.  The defaults are deliberately simple and
remain fixed across later protocol comparisons unless an experiment explicitly
changes them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DCFConfig:
    """Parameters used by the minimum basic-access DCF procedure."""

    slot_time: float = 20e-6
    sifs_time: float = 10e-6
    difs_time: float = 50e-6
    propagation_delay: float = 1e-6

    cw_min: int = 15
    cw_max: int = 1023
    retry_limit: int = 7

    data_rate_bps: float = 2_000_000.0
    basic_rate_bps: float = 1_000_000.0
    mac_header_bytes: int = 34
    ack_size_bytes: int = 14

    random_seed: int = 7

    def __post_init__(self) -> None:
        positive_times = {
            "slot_time": self.slot_time,
            "sifs_time": self.sifs_time,
            "difs_time": self.difs_time,
            "propagation_delay": self.propagation_delay,
        }
        for name, value in positive_times.items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative.")

        if self.cw_min < 0:
            raise ValueError("cw_min cannot be negative.")
        if self.cw_max < self.cw_min:
            raise ValueError("cw_max must be greater than or equal to cw_min.")
        if self.retry_limit < 0:
            raise ValueError("retry_limit cannot be negative.")
        if self.data_rate_bps <= 0 or self.basic_rate_bps <= 0:
            raise ValueError("PHY rates must be positive.")
        if self.mac_header_bytes < 0:
            raise ValueError("mac_header_bytes cannot be negative.")
        if self.ack_size_bytes <= 0:
            raise ValueError("ack_size_bytes must be positive.")

    def data_tx_time(self, payload_size_bytes: int) -> float:
        """Return DATA frame serialization time for one packet."""
        if payload_size_bytes <= 0:
            raise ValueError("payload_size_bytes must be positive.")
        frame_bytes = self.mac_header_bytes + payload_size_bytes
        return frame_bytes * 8 / self.data_rate_bps

    @property
    def ack_tx_time(self) -> float:
        """Return ACK frame serialization time."""
        return self.ack_size_bytes * 8 / self.basic_rate_bps

    def expected_success_delay(self, payload_size_bytes: int, backoff_slots: int) -> float:
        """Return the ideal no-contention one-hop delay used by tests."""
        if backoff_slots < 0:
            raise ValueError("backoff_slots cannot be negative.")
        return (
            self.difs_time
            + backoff_slots * self.slot_time
            + self.data_tx_time(payload_size_bytes)
            + self.propagation_delay
            + self.sifs_time
            + self.ack_tx_time
            + self.propagation_delay
        )
