from __future__ import annotations

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import STAGE, load_json, semantic_result_files, terminal_accounting, write_json


def main() -> int:
    checks = []
    for path in semantic_result_files():
        result = load_json(path)
        passed, detail = terminal_accounting(result)
        checks.append({"file": path.name, "passed": passed, "detail": detail})
    outcome = {"passed": bool(checks) and all(c["passed"] for c in checks), "checks": checks}
    write_json(STAGE / "results" / "audit" / "result_integrity.json", outcome)
    return 0 if outcome["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
