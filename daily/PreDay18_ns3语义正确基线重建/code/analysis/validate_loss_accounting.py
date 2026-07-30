from __future__ import annotations

from typing import Any


def validate(result: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    terminal_sum = sum(result["terminal_counts"].values())
    if terminal_sum != result["created"]:
        issues.append(f"created={result['created']} terminal_sum={terminal_sum}")
    if result["unknown_loss"] != 0:
        issues.append(f"unknown_loss={result['unknown_loss']}")
    if result["active_reservations_after_run"] != 0:
        issues.append("active reservation remains")
    return not issues, issues
