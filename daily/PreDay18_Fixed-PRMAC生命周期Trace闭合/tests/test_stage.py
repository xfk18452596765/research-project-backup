import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_audit_is_instrumentation_only():
    subprocess.run(['python', str(ROOT/'code/run_lifecycle_audit.py')], check=True)
    import json
    audit = json.loads((ROOT/'results/audit/lifecycle_patch_scope.json').read_text(encoding='utf-8'))
    assert audit['historical_evidence_immutable']
    assert audit['patch_nonempty']
    assert audit['forbidden_tokens_absent']

def test_no_rl_or_day18_changes():
    changed = subprocess.check_output(['git','diff','--name-only','e86cb56'], cwd=ROOT.parents[1], text=True).splitlines()
    assert all(path.startswith(ROOT.relative_to(ROOT.parents[1]).as_posix()) for path in changed)
