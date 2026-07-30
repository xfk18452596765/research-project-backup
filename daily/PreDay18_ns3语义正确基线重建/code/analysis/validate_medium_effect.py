from __future__ import annotations

from typing import Any


def validate(result: dict[str, Any], events: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    effect = result["medium_effect"]
    if effect["reserved_access_events"] <= 0:
        issues.append("no Txop reserved-access trace")
    if effect["local_block_events"] <= 0:
        issues.append("no local conflict block trace")
    if not any(e["event"] == "RESERVATION_RELEASED" for e in events):
        issues.append("no reservation release trace")
    if not any(
        e["event"] == "DCF_ACCESS_GRANTED"
        and "reserved-zero-random-backoff" in e["reason"]
        for e in events
    ):
        issues.append("reserved path did not bypass random backoff")
    return not issues, issues
