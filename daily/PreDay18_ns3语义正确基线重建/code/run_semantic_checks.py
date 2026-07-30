from __future__ import annotations

from common import run_case


def main() -> int:
    run_case(
        protocol="dcf",
        scenario="calibration",
        hops=6,
        packets=1,
        seed=7,
    )
    for hops in (1, 2, 4, 6):
        run_case(protocol="dcf", hops=hops, packets=1, seed=7)
    for hops in (2, 4, 6):
        run_case(protocol="fixed", hops=hops, packets=1, seed=7)
    run_case(
        protocol="fixed",
        scenario="reservation-conflict",
        hops=2,
        packets=1,
        seed=7,
    )
    for scenario in ("multiflow-m1", "multiflow-m2"):
        run_case(
            protocol="fixed",
            scenario=scenario,
            hops=6,
            packets=5,
            flows=2,
            seed=7,
        )
    run_case(
        protocol="fixed",
        scenario="hidden",
        hops=1,
        packets=5,
        flows=2,
        seed=7,
        load="high",
    )
    print("semantic checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
