#!/usr/bin/env python3
"""Records a fail-closed gate ledger; PASS is never inferred from absent evidence."""
from __future__ import annotations
import json
from pathlib import Path
STAGE = Path(__file__).resolve().parents[1]
def main():
    out = STAGE / "results" / "gates"; out.mkdir(parents=True, exist_ok=True)
    gates = {f"Gate{i}": {"status": "HOLD", "reason": "No real ns-3.43 A/B execution evidence recorded"} for i in range(8)}
    gates["Gate0"] = {"status": "PASS", "reason": "V2 scope and historical evidence guard established"}
    (out / "gate_ledger.json").write_text(json.dumps(gates, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps(gates, indent=2))
if __name__ == "__main__": main()
