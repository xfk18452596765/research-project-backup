from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any


def validate(events: list[dict[str, Any]], hops: int) -> tuple[bool, list[str]]:
    issues: list[str] = []
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[(event["flow_id"], event["packet_id"])].append(event)
    for identity, packet_events in grouped.items():
        sends = [
            event
            for event in packet_events
            if event["event"] in ("SOURCE_MAC_SEND", "HOP_MAC_SEND")
        ]
        receives = [
            event for event in packet_events if event["event"] == "HOP_MAC_RX"
        ]
        for send in sends:
            hop = send["hop_index"]
            if hop == 0:
                continue
            prior = [
                event
                for event in receives
                if event["node_id"] == send["node_id"]
                and event["time_us"] <= send["time_us"]
            ]
            if not prior:
                issues.append(f"{identity}: hop {hop} sent before local receive")
        hop_values = {event["hop_index"] for event in sends}
        if hop_values and max(hop_values) >= hops:
            issues.append(f"{identity}: invalid outgoing hop index")
    return not issues, issues


if __name__ == "__main__":
    import json
    import sys

    trace_path = Path(sys.argv[1])
    hop_count = int(sys.argv[2])
    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    passed, messages = validate(records, hop_count)
    print(json.dumps({"passed": passed, "issues": messages}, indent=2))
    raise SystemExit(0 if passed else 1)
