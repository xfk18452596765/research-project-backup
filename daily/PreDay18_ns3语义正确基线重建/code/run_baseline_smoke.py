from __future__ import annotations

from common import run_case


def main() -> int:
    for protocol in ("dcf", "fixed"):
        for hops in (2, 4, 6):
            for traffic in ("periodic", "poisson"):
                for seed in (7, 17, 27):
                    run_case(
                        protocol=protocol,
                        hops=hops,
                        packets=10,
                        traffic=traffic,
                        load="low",
                        seed=seed,
                    )
        for traffic in ("periodic", "poisson"):
            for seed in (7, 17, 27):
                run_case(
                    protocol=protocol,
                    hops=6,
                    packets=100,
                    traffic=traffic,
                    load="high",
                    seed=seed,
                )
    print("baseline smoke matrix completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
