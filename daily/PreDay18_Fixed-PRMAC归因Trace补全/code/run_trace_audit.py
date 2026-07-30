from common import *
import subprocess
from instrument_source import SRC,OUT,main as build
def main():
 build();before=[manifest(x) for x in HIST]; baseline=read(REPO/'daily/PreDay18_ns3语义正确基线重建/results/decision/baseline_readiness.json');attrib=read(REPO/'daily/PreDay18_Fixed-PRMAC失败归因补强/results/decision/attribution_decision.json')
 patch=STAGE/'ns3/patches/attribution-trace-completion.patch';patch.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['git','diff','--no-index','--',str(SRC),str(OUT)],stdout=patch.open('w',encoding='utf8'),check=False)
 data={'historical':[manifest(x) for x in HIST],'historical_unchanged':before==[manifest(x) for x in HIST],'semantic_decision':baseline['baseline_decision'],'attribution_decision':attrib['decision'],'clean_source_sha256':sha(SRC),'trace_completion_patch_sha256':sha(patch),'final_patched_source_sha256':sha(OUT),'scope':'only trace serialization gate, timestamps and read-only field snapshots'}
 write(STAGE/'results/audit/historical_evidence_sha256.json',{'manifests':before});write(STAGE/'results/audit/semantic_baseline_manifest.json',{'decision':baseline['baseline_decision']});write(STAGE/'results/audit/attribution_hold_manifest.json',{'decision':attrib['decision'],'sha256':sha(REPO/'daily/PreDay18_Fixed-PRMAC失败归因补强/results/decision/attribution_decision.json')});write(STAGE/'results/audit/trace_patch_scope.json',data)
 print(data['trace_completion_patch_sha256'])
if __name__=='__main__':main()
