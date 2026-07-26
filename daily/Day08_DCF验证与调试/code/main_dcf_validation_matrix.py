"""Run the Day08 DCF validation matrix."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from dcf_validation import (  # noqa: E402
    LOAD_PROFILES,
    aggregate_validation_rows,
    run_converging_collision_smoke,
    run_periodic_chain_case,
    write_csv,
    write_json,
)


HOP_COUNTS = (2, 4, 6)
SEEDS = (7, 17, 27)
PACKETS_PER_RUN = 8


def main() -> None:
    results_dir = CURRENT_DIR.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    raw_rows: list[dict[str, int | float | str]] = []

    print("=== Day08: DCF validation matrix ===")
    print(
        f"hops={HOP_COUNTS}, seeds={SEEDS}, "
        f"packets_per_run={PACKETS_PER_RUN}"
    )

    for hop_count in HOP_COUNTS:
        for profile in LOAD_PROFILES:
            for seed in SEEDS:
                _, row = run_periodic_chain_case(
                    hop_count,
                    packet_count=PACKETS_PER_RUN,
                    interarrival_time=profile.interarrival_time,
                    seed=seed,
                    log_enabled=False,
                )
                row["load_level"] = profile.name
                raw_rows.append(row)
                print(
                    f"{hop_count} hops | {profile.name:<6} | seed={seed:<2} | "
                    f"delay={float(row['average_end_to_end_delay']):.9f}s | "
                    f"p95={float(row['p95_end_to_end_delay']):.9f}s | "
                    f"delivery={float(row['delivery_ratio']):.3f} | "
                    f"collisions={int(row['shared_collision_events'])} | "
                    f"retries={int(row['retransmissions'])}"
                )

    aggregate_rows = aggregate_validation_rows(raw_rows)
    raw_path = write_csv(results_dir / "dcf_validation_raw.csv", raw_rows)
    aggregate_path = write_csv(
        results_dir / "dcf_validation_aggregate.csv",
        aggregate_rows,
    )

    smoke_context, smoke_result = run_converging_collision_smoke(
        log_enabled=False
    )
    smoke_path = write_json(
        results_dir / "dcf_converging_collision_smoke.json",
        smoke_result,
    )

    summary_payload = {
        "experiment_scope": {
            "hop_counts": list(HOP_COUNTS),
            "seeds": list(SEEDS),
            "packets_per_run": PACKETS_PER_RUN,
            "load_profiles": [
                {
                    "name": profile.name,
                    "interarrival_time": profile.interarrival_time,
                }
                for profile in LOAD_PROFILES
            ],
        },
        "aggregate_rows": aggregate_rows,
        "converging_collision_smoke": smoke_result,
    }
    summary_path = write_json(
        results_dir / "dcf_validation_summary.json",
        summary_payload,
    )

    print("\n=== Converging-flow collision smoke ===")
    print(
        f"delivered={smoke_result['delivered_packets']}, "
        f"collisions={smoke_result['shared_collision_events']}, "
        f"retries={smoke_result['retransmissions']}, "
        f"freezes={smoke_result['backoff_freezes']}"
    )

    print("\nSaved:")
    print(f"- {raw_path}")
    print(f"- {aggregate_path}")
    print(f"- {smoke_path}")
    print(f"- {summary_path}")


if __name__ == "__main__":
    main()
