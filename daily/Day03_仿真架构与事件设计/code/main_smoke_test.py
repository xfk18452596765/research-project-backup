"""Day03 smoke test."""
from channel import Channel
from metrics import MetricsCollector
from node import Node
from packet import Packet
from simulator import Simulator

def main() -> None:
    sim = Simulator()
    channel = Channel()
    metrics = MetricsCollector()
    node0, node1 = Node(0), Node(1)
    node0.neighbors.add(1)
    node1.neighbors.add(0)
    packet = Packet(1, 0, 1, created_at=0.001, route=(0, 1))
    order: list[str] = []

    def arrival() -> None:
        metrics.record_created(packet)
        assert node0.enqueue(packet)
        order.append("arrival")

    def tx_start() -> None:
        assert node0.dequeue() is packet
        channel.occupy(0, sim.now, 0.002)
        order.append("tx_start")
        sim.schedule(0.002, release, event_type="TX_END", priority=0)

    def release() -> None:
        channel.release()
        order.append("release")

    def delivery() -> None:
        metrics.record_delivered(packet, sim.now)
        order.append("delivery")

    sim.schedule_at(0.001, arrival, event_type="PACKET_ARRIVAL", priority=40)
    sim.schedule_at(0.003, tx_start, event_type="TX_START", priority=20)
    sim.schedule_at(0.005, delivery, event_type="RX_SUCCESS", priority=10)
    sim.run(until=0.010)

    assert order == ["arrival", "tx_start", "release", "delivery"]
    assert abs(metrics.delays[0] - 0.004) < 1e-12
    assert channel.is_idle(sim.now)
    print("Smoke test passed.")
    print(metrics.summary())

if __name__ == "__main__":
    main()
