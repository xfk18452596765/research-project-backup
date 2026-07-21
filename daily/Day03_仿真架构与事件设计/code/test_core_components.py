"""Day03 core component boundary tests."""

from channel import Channel
from metrics import MetricsCollector
from node import Node
from packet import Packet
from simulator import Simulator


def test_event_priority_order():
    sim = Simulator(log_enabled=False)
    order = []
    sim.schedule_at(1.0, lambda: order.append("p0"), priority=0)
    sim.schedule_at(1.0, lambda: order.append("p20"), priority=20)
    sim.run()
    assert order == ["p0", "p20"]


def test_same_priority_insertion_order():
    sim = Simulator(log_enabled=False)
    order = []
    sim.schedule_at(1.0, lambda: order.append("first"), priority=10)
    sim.schedule_at(1.0, lambda: order.append("second"), priority=10)
    sim.run()
    assert order == ["first", "second"]


def test_invalid_event_time():
    sim = Simulator(log_enabled=False)
    try:
        sim.schedule(-0.1, lambda: None)
    except ValueError:
        pass
    else:
        raise AssertionError("Negative delay should raise ValueError.")

    sim.schedule_at(1.0, lambda: None)
    sim.run()
    try:
        sim.schedule_at(0.5, lambda: None)
    except ValueError:
        pass
    else:
        raise AssertionError("Scheduling in the past should raise ValueError.")


def test_node_queue_limit():
    node = Node(node_id=0, queue_limit=1)
    p1 = Packet(packet_id=1, source=0, destination=1, created_at=0.0, route=(0, 1))
    p2 = Packet(packet_id=2, source=0, destination=1, created_at=0.0, route=(0, 1))
    assert node.enqueue(p1) is True
    assert node.enqueue(p2) is False
    assert node.queue_length == 1
    assert node.peek() is p1
    assert node.dequeue() is p1
    assert node.dequeue() is None


def test_channel_busy_protection():
    channel = Channel()
    assert channel.is_idle(0.0)
    channel.occupy(node_id=0, now=0.0, duration=0.01)
    assert not channel.is_idle(0.005)
    assert channel.owner == 0
    try:
        channel.occupy(node_id=1, now=0.005, duration=0.01)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Busy channel should reject a second owner.")
    assert channel.is_idle(0.01)
    assert channel.owner is None


def test_packet_properties():
    packet = Packet(
        packet_id=3,
        source=0,
        destination=3,
        created_at=0.2,
        route=(0, 1, 2, 3),
    )
    assert packet.current_node == 0
    assert packet.remaining_hops == 3
    packet.current_hop_index = 2
    assert packet.current_node == 2
    assert packet.remaining_hops == 1
    packet.delivered_at = 0.8
    assert abs(packet.end_to_end_delay - 0.6) < 1e-12


def test_metrics_collector():
    metrics = MetricsCollector()
    packet = Packet(packet_id=4, source=0, destination=1, created_at=0.1, route=(0, 1))
    metrics.record_created(packet)
    metrics.record_delivered(packet, delivered_at=0.4)
    summary = metrics.summary()
    assert summary["created_packets"] == 1
    assert summary["delivered_packets"] == 1
    assert abs(summary["average_delay"] - 0.3) < 1e-12
    assert abs(summary["delivery_ratio"] - 1.0) < 1e-12


def main():
    tests = [
        test_event_priority_order,
        test_same_priority_insertion_order,
        test_invalid_event_time,
        test_node_queue_limit,
        test_channel_busy_protection,
        test_packet_properties,
        test_metrics_collector,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("\nAll Day03 core component tests passed.")


if __name__ == "__main__":
    main()
