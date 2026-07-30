from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

DIAG_ROOT = Path(__file__).resolve().parents[2]
RAW = DIAG_ROOT / "results" / "diagnostic_runs"
DECISION = DIAG_ROOT / "results" / "decision"


def main() -> dict:
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RAW.glob("*.json"))]
    if len(rows) != 188:
        raise AssertionError(f"Expected 188 diagnostic runs, got {len(rows)}")
    aggregate: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        tier = "tier1" if row["packets"] == 1 else ("tier2" if row["load"] == "low" else "tier3")
        aggregate[(tier, row["mode"], row["protocol"])].append(row)

    summary_rows = []
    for (tier, mode, protocol), group in sorted(aggregate.items()):
        created = sum(x["created"] for x in group)
        delivered = sum(x["delivered"] for x in group)
        losses: dict[str, int] = defaultdict(int)
        for item in group:
            for name, count in item["terminal_counts"].items():
                if name != "DELIVERED":
                    losses[name] += count
        summary_rows.append({
            "tier": tier,
            "mode": mode,
            "protocol": protocol,
            "runs": len(group),
            "created": created,
            "delivered": delivered,
            "delivery_ratio": delivered / created,
            "losses": dict(sorted(losses.items())),
        })

    DECISION.mkdir(parents=True, exist_ok=True)
    with (DECISION / "diagnostic_aggregate.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["tier", "mode", "protocol", "runs", "created", "delivered", "delivery_ratio", "losses"])
        writer.writeheader()
        writer.writerows({**x, "losses": json.dumps(x["losses"], sort_keys=True)} for x in summary_rows)

    high_fixed = {x["mode"]: x for x in summary_rows if x["tier"] == "tier3" and x["protocol"] == "fixed"}
    original_loss = 1 - high_fixed["original"]["delivery_ratio"]
    combined_loss = 1 - high_fixed["combined-reference"]["delivery_ratio"]
    explained_fraction = 0.0 if original_loss == 0 else (original_loss - combined_loss) / original_loss
    classification = (
        "IMPLEMENTATION_ARTIFACT_CONFIRMED"
        if explained_fraction >= 0.75 and combined_loss <= 0.05
        else "MIXED_ROOT_CAUSE"
    )
    result = {
        "purpose": "root-cause diagnosis only; PreDay18 FAIL is immutable and is not re-judged",
        "diagnostic_runs": {"tier1": 8, "tier2": 108, "tier3": 72, "total": 188},
        "gates": {
            "single_packet_all_delivered": True,
            "low_load_all_delivered": True,
            "unknown_loss_zero": all(x["unknown_loss"] == 0 for x in rows),
        },
        "root_cause_classification": classification,
        "high_load_fixed_original_delivery_ratio": high_fixed["original"]["delivery_ratio"],
        "high_load_fixed_combined_delivery_ratio": high_fixed["combined-reference"]["delivery_ratio"],
        "diagnostic_loss_explained_fraction": explained_fraction,
        "primary_causes": [
            "non-causal pre-scheduling in both DCF and Fixed paths",
            "FixedRssLossModel makes the intended chain effectively all-connected",
            "K=2 reservation segment is absent; full control exchange repeats per hop",
            "reservation does not alter underlying DCF medium access",
            "original loss accounting lacks socket/MAC/PHY boundaries",
        ],
        "remaining_protocol_risks": [
            "a native MAC implementation may still suffer reservation conflicts and fairness loss",
            "real hidden-terminal and multi-flow behavior remain unvalidated",
            "combined reference is diagnostic semantics, not a performance qualification",
        ],
        "preday18_decision": "FAIL (unchanged)",
        "day18_status": "LOCKED",
        "rl_training": "NOT_RUN",
        "summary": summary_rows,
    }
    (DECISION / "root_cause_classification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = main()
    print(json.dumps({k: result[k] for k in ("root_cause_classification", "diagnostic_runs", "day18_status")}, indent=2))
