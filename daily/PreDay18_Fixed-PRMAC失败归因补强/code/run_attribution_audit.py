from __future__ import annotations
import subprocess
from common import *
def git(*x): return subprocess.check_output(['git',*x],cwd=REPO,text=True).strip()
def main():
 head=git('rev-parse','HEAD'); branch=git('branch','--show-current'); status=git('status','--short')
 baseline=read(REPO/'daily/PreDay18_ns3语义正确基线重建/results/decision/baseline_readiness.json')
 stop=read(REPO/'daily/PreDay18_语义正确基线止损复验/results/decision/stop_loss_decision.json')
 redesign=read(REPO/'daily/PreDay18_Fixed-PRMAC机制重设计/results/decision/redesign_decision.json')
 m=[manifest(x) for x in HIST]
 write(STAGE/'results/audit/historical_evidence_sha256.json',{'base_commit':head,'branch':branch,'manifests':m})
 write(STAGE/'results/audit/semantic_baseline_manifest.json',{'decision':baseline.get('baseline_decision'),'source_hashes':read(REPO/'daily/PreDay18_ns3语义正确基线重建/results/audit/source_hashes.json')})
 write(STAGE/'results/audit/stop_loss_failure_manifest.json',{'decision':stop.get('decision'),'sha256':sha(REPO/'daily/PreDay18_语义正确基线止损复验/results/decision/stop_loss_decision.json')})
 write(STAGE/'results/audit/redesign_hold_manifest.json',{'decision':redesign.get('decision'),'attribution_fraction':redesign.get('attribution_fraction'),'sha256':sha(REPO/'daily/PreDay18_Fixed-PRMAC机制重设计/results/decision/redesign_decision.json')})
 source=REPO/'daily/PreDay18_语义正确基线止损复验/ns3/source/preday18-stop-loss-retest.cc'; schema=read(STAGE/'configs/trace_schema.json')
 write(STAGE/'results/audit/trace_only_patch_audit.json',{'trace_only':True,'patch_sha256':None,'instrumented_source_sha256':sha(source),'semantic_behavior_code_changed':False,'method':'identity overlay; legacy source is copied to an isolated WSL scratch path only','required_trace_schema':schema,'behavior_equivalence':'PENDING_REPLAY'})
 ok=baseline.get('baseline_decision')=='BASELINE_READY' and stop.get('decision')=='FAIL' and redesign.get('decision')=='REDESIGN_HOLD'
 print('AUDIT_PASS' if ok else 'AUDIT_FAIL');return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
