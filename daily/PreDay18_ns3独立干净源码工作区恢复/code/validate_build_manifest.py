#!/usr/bin/env python3
import json
from pathlib import Path
p = Path(__file__).resolve().parents[1] / "results" / "manifests" / "patch_chain_manifest.json"
data = json.loads(p.read_text(encoding="utf-8"))
assert data["decision"] in {"NS3_WORKSPACE_READY", "NS3_WORKSPACE_HOLD"}
print(data["decision"])
