from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def validate(events: list[dict[str, Any]], hops: int) -> tuple[bool, list[str]]:
    issues: list[str] = []
    per_packet: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        per_packet[(event["flow_id"], event["packet_id"])].append(event)
    for identity, packet_events in per_packet.items():
        heads = [e for e in packet_events if e["event"] == "LOCAL_FIFO_HEAD"]
        if len(heads) != math.ceil(hops / 2):
            issues.append(
                f"{identity}: segment heads={len(heads)} expected={math.ceil(hops / 2)}"
            )
        for head in heads:
            text = head["reason"]
            if "effective_hops=" not in text or int(text.rsplit("=", 1)[1]) > 2:
                issues.append(f"{identity}: invalid effective_hops")
        for segment in {e["segment_id"] for e in heads}:
            segment_events = [e for e in packet_events if e["segment_id"] == segment]
            ack = [e["time_us"] for e in segment_events if e["event"] == "PR_ACK_RX"]
            data = [
                e["time_us"]
                for e in segment_events
                if e["event"] == "RESERVED_DATA_ENQUEUE"
                and e["frame_type"] == "DATA"
            ]
            if data and (not ack or min(data) < min(ack)):
                issues.append(f"{identity}: segment {segment} DATA before PR_ACK")
        for previous, current in zip(heads, heads[1:]):
            released = [
                e
                for e in packet_events
                if e["segment_id"] == previous["segment_id"]
                and e["event"] == "SEGMENT_COMPLETED"
                and e["time_us"] <= current["time_us"]
            ]
            if not released:
                issues.append(f"{identity}: next segment before RELEASE completion")
    return not issues, issues


def validate_retry(events: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    required = {
        "PR_NACK_TX",
        "PR_NACK_RX",
        "RESERVATION_ATTEMPT_REJECTED",
        "DIFS_BEB_BACKOFF",
        "PACKET_DELIVERED",
    }
    observed = {event["event"] for event in events}
    for event in sorted(required - observed):
        issues.append(f"missing retry event {event}")
    backoffs = [event for event in events if event["event"] == "DIFS_BEB_BACKOFF"]
    if not backoffs or "CW=31," not in backoffs[0]["reason"]:
        issues.append("first retry did not use CW=31")
    attempts = {
        event["attempt"]
        for event in events
        if event["event"] in ("PR_REQ_TX", "PR_REQ_RX")
    }
    if not {0, 1}.issubset(attempts):
        issues.append(f"fresh attempt not observed: {sorted(attempts)}")
    return not issues, issues
