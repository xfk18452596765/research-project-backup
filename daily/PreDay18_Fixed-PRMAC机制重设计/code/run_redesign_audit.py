from __future__ import annotations
import subprocess
from datetime import datetime,timezone
from common import *
EXPECTED='1782431497d4710e02fd8c97fd9de24ae30372a0'
def git(*a):return subprocess.check_output(['git',*a],cwd=REPO,text=True,encoding='utf-8',errors='replace').strip()
def main():
 failures=[]; head=git('rev-parse','HEAD'); branch=git('branch','--show-current'); status=git('status','--short')
 if head!=EXPECTED: failures.append('base commit mismatch')
 if branch!='main': failures.append('branch is not main')
 unexpected=[line for line in status.splitlines() if 'daily/PreDay18_Fixed-PRMAC机制重设计/' not in line.replace('\\','/')]
 if unexpected: failures.append('unexpected working-tree changes: '+str(unexpected))
 baseline=load(REPO/'daily/PreDay18_ns3语义正确基线重建/results/decision/baseline_readiness.json')
 if baseline.get('baseline_decision')!='BASELINE_READY': failures.append('semantic baseline is not BASELINE_READY')
 registry=STAGE/'configs/candidate_registry.json'; policy=STAGE/'configs/redesign_readiness_policy.json'
 dump(STAGE/'results/audit/baseline_input_verification.json',{'time_utc':datetime.now(timezone.utc).isoformat(),'base_commit':head,'branch':branch,'semantic_baseline_decision':baseline.get('baseline_decision'),'semantic_source_sha256':load(REPO/'daily/PreDay18_ns3语义正确基线重建/results/audit/source_hashes.json')['patched_source_sha256'],'candidate_registry_sha256':sha(registry),'policy_sha256':sha(policy),'failures':failures})
 dump(STAGE/'results/audit/historical_evidence_start.json',{'manifests':[manifest(p) for p in HISTORICAL]})
 print('AUDIT_PASS' if not failures else 'AUDIT_FAIL: '+ '; '.join(failures)); return 0 if not failures else 1
if __name__=='__main__':raise SystemExit(main())
