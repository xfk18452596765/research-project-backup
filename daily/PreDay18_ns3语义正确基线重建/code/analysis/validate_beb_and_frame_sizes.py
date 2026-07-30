from __future__ import annotations

from typing import Any


def expected_cw(retry: int) -> int:
    return min((15 + 1) * (2**retry) - 1, 1023)


def validate_source(source: str) -> tuple[bool, list[str]]:
    issues: list[str] = []
    expected_sizes: dict[str, int] = {
        "PR_REQ_BYTES": 36,
        "PR_ACK_BYTES": 24,
        "PR_NACK_BYTES": 24,
        "H_ACK_BYTES": 14,
        "RELEASE_BYTES": 20,
        "DATA_BYTES": 1024,
    }
    for symbol, value in expected_sizes.items():
        if f"{symbol} = {value}" not in source:
            issues.append(f"missing frozen {symbol}={value}")
    if "Create<Packet>(configured - header.GetSerializedSize())" not in source:
        issues.append("frame padding does not subtract serialized header")
    sequence = [expected_cw(retry) for retry in range(1, 9)]
    if sequence != [31, 63, 127, 255, 511, 1023, 1023, 1023]:
        issues.append(f"BEB formula regression: {sequence}")
    return not issues, issues
