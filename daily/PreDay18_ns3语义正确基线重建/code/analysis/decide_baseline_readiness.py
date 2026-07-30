from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def decide(gates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ready = all(gates[f"Gate {number}"]["passed"] for number in range(7))
    return {
        "gates": gates,
        "baseline_decision": "BASELINE_READY" if ready else "BASELINE_HOLD",
        "Day18_status": "LOCKED",
        "stop_loss_pass_rejudged": False,
        "RL_run": False,
    }


if __name__ == "__main__":
    source = Path(__import__("sys").argv[1])
    outcome = decide(json.loads(source.read_text(encoding="utf-8")))
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
