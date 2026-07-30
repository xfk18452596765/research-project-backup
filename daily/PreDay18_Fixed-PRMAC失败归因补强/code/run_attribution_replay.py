from __future__ import annotations
import gzip,json,subprocess
from pathlib import Path
from common import *
M=read(STAGE/'configs/replay_matrix.json'); WORK='/home/xfk/workspace/ns-3.43-fixed-prmac-baseline'; EXE=WORK+'/build/scratch/ns3.43-preday18-stop-loss-retest-default'
def wp(p):
 q=p.resolve(); return '/mnt/'+q.drive[0].lower()+q.as_posix().split(':',1)[1]
def run(kind,p,h,t,l,s):
 rid=f'{kind}-{p}-{h}hop-{l}-{t}-seed{s}'; raw=STAGE/'results/raw_traces'/(rid+'.jsonl');out=STAGE/'results/scenario_level'/(rid+'.json');raw.parent.mkdir(parents=True,exist_ok=True);out.parent.mkdir(parents=True,exist_ok=True)
 cmd=f'{EXE} --protocol={p} --scenario=chain --hops={h} --packets={n} --traffic={t} --load={l} --seed={s} --trace={wp(raw)} --output={wp(out)}'
 r=subprocess.run(['wsl.exe','-e','bash','-lc',cmd],cwd=REPO,capture_output=True,timeout=180)
 if r.returncode: return rid,False,(r.stderr or b'')[-500:].decode('utf8','replace')
 with gzip.open(str(raw)+'.gz','wt',encoding='utf8') as z:z.write(raw.read_text(encoding='utf8'))
 raw.unlink();return rid,True,''
def main():
 global n;n=200; cases=[('core',p,h,t,l,s) for p in M['protocols'] for h,l,t in M['core'] for s in M['seeds']]
 # calibration matrix required by the task
 cases += [('single',p,h,'periodic','low',7) for p in M['protocols'] for h in (2,4,6)]
 cases += [('low',p,h,t,'low',s) for p in M['protocols'] for h in (2,4,6) for t in ('periodic','poisson') for s in (7,17,27)]
 results=[]
 for i,c in enumerate(cases,1):
  n=1 if c[0]=='single' else (10 if c[0]=='low' else 200);results.append(run(*c));print(f'{i}/{len(cases)} {results[-1][0]}')
 write(STAGE/'results/scenario_level/replay_execution.json',{'expected_core':120,'expected_single':6,'expected_low':36,'completed':sum(x[1] for x in results),'failed':[x for x in results if not x[1]]})
 return 0 if all(x[1] for x in results) else 2
if __name__=='__main__':raise SystemExit(main())
