from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any


def validate_calibration(
    events: list[dict[str, Any]], node_count: int, output_dir: Path
) -> tuple[bool, list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sent: dict[int, tuple[int, int]] = {}
    received: set[tuple[int, int]] = set()
    for event in events:
        if event["event"] == "PROBE_TX":
            target = int(event["reason"].split("=", 1)[1])
            sent[event["packet_id"]] = (event["node_id"], target)
        elif event["event"] == "PROBE_RX" and event["packet_id"] in sent:
            received.add(sent[event["packet_id"]])

    spacing = 20.0
    tx_power = 22.0
    exponent = 4.0
    reference_loss = 46.6777
    sensitivity = -85.0
    cca = -93.0
    connectivity: list[list[bool]] = []
    carrier_sense: list[list[bool]] = []
    rss_matrix: list[list[float | None]] = []
    issues: list[str] = []
    for source in range(node_count):
        connectivity_row: list[bool] = []
        carrier_row: list[bool] = []
        rss_row: list[float | None] = []
        for target in range(node_count):
            if source == target:
                connectivity_row.append(True)
                carrier_row.append(True)
                rss_row.append(None)
                continue
            distance = abs(source - target) * spacing
            rss = tx_power - (
                reference_loss + 10.0 * exponent * math.log10(max(1.0, distance))
            )
            decoded = (source, target) in received
            connectivity_row.append(decoded)
            carrier_row.append(rss >= cca)
            rss_row.append(round(rss, 6))
            if abs(source - target) == 1 and not decoded:
                issues.append(f"adjacent {source}->{target} did not decode")
            if abs(source - target) >= 2 and decoded:
                issues.append(f"non-adjacent {source}->{target} decoded directly")
        connectivity.append(connectivity_row)
        carrier_sense.append(carrier_row)
        rss_matrix.append(rss_row)

    (output_dir / "connectivity_matrix.json").write_text(
        json.dumps(
            {"nodes": node_count, "matrix": connectivity}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "carrier_sense_matrix.json").write_text(
        json.dumps(
            {
                "nodes": node_count,
                "threshold_dbm": cca,
                "matrix": carrier_sense,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (output_dir / "topology_calibration.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["source", "target", "distance_m", "rss_dbm", "decoded", "carrier_sense"]
        )
        for source in range(node_count):
            for target in range(node_count):
                if source == target:
                    continue
                writer.writerow(
                    [
                        source,
                        target,
                        abs(source - target) * spacing,
                        rss_matrix[source][target],
                        connectivity[source][target],
                        carrier_sense[source][target],
                    ]
                )
    return not issues, issues
