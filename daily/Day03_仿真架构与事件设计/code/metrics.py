"""Metrics collection."""
from dataclasses import dataclass, field
from packet import Packet, PacketStatus

@dataclass
class MetricsCollector:
    created_packets: int = 0
    delivered_packets: int = 0
    dropped_packets: int = 0
    retransmissions: int = 0
    delays: list[float] = field(default_factory=list)

    def record_created(self, packet: Packet) -> None:
        self.created_packets += 1

    def record_delivered(self, packet: Packet, delivered_at: float) -> None:
        packet.status = PacketStatus.DELIVERED
        packet.delivered_at = delivered_at
        self.delivered_packets += 1
        if packet.end_to_end_delay is not None:
            self.delays.append(packet.end_to_end_delay)

    def summary(self) -> dict[str, float | int]:
        average_delay = sum(self.delays) / len(self.delays) if self.delays else 0.0
        ratio = self.delivered_packets / self.created_packets if self.created_packets else 0.0
        return {"created_packets": self.created_packets,
                "delivered_packets": self.delivered_packets,
                "average_delay": average_delay,
                "delivery_ratio": ratio}
