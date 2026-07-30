from common import *
import subprocess
WORK='/home/xfk/workspace/ns-3.43-fixed-prmac-baseline';EXE=WORK+'/build/scratch/ns3.43-preday18-fixed-prmac-trace-default'
def wp(p):
 q=p.resolve();return '/mnt/'+q.drive[0].lower()+q.as_posix().split(':',1)[1]
def call(mode,p,h,t,l,seed,n,tag):
 root=STAGE/'results'/'equivalence';root.mkdir(parents=True,exist_ok=True);out=root/f'{tag}-{mode}.json';tr=root/f'{tag}-{mode}.jsonl'
 cmd=f'{EXE} --protocol={p} --scenario=chain --hops={h} --traffic={t} --load={l} --seed={seed} --packets={n} --traceEnabled={str(mode=="enabled").lower()} --output={wp(out)} --trace={wp(tr)}'
 x=subprocess.run(['wsl.exe','-e','bash','-lc',cmd],capture_output=True,timeout=180)
 return x.returncode,out,tr
def same(a,b):
 x=read(a);y=read(b);return all(x[k]==y[k] for k in ['created','delivered','terminal_counts','packets_detail','active_reservations_after_run'])
def main():
 failures=[];runs=0
 for p in ('dcf','fixed'):
  for h in (2,4,6):
   for t in ('periodic','poisson'):
    for l in ('low','high'):
     for seed in (7,17,27):
      tag=f'{p}-{h}-{t}-{l}-{seed}';a=call('disabled',p,h,t,l,seed,50,tag);b=call('enabled',p,h,t,l,seed,50,tag);runs+=2
      if not a[1].exists() or not b[1].exists() or not same(a[1],b[1]):failures.append(tag)
 # Calibration gates; only execute when equivalence passes.
 write(STAGE/'results/equivalence/summary.json',{'runs':runs,'passed':not failures,'failures':failures})
 if failures: print('TRACE_INVALID');return 2
 calibration=[]
 for phase,n,seeds in [('single',1,(7,)),('low',10,(7,17,27))]:
  for p in ('dcf','fixed'):
   for h in (2,4,6):
    for t in (('periodic',) if phase=='single' else ('periodic','poisson')):
     for seed in seeds:
      tag=f'{phase}-{p}-{h}-{t}-{seed}';r=call('enabled',p,h,t,'low',seed,n,tag);calibration.append({'id':tag,'ok':r[0]==0,'trace':r[2].name})
 write(STAGE/'results/calibration/summary.json',{'single_expected':6,'single_completed':sum(x['ok'] for x in calibration if x['id'].startswith('single-')),'low_expected':36,'low_completed':sum(x['ok'] for x in calibration if x['id'].startswith('low-')),'runs':calibration})
 print('EQUIVALENCE_PASS' if not failures else 'TRACE_INVALID');return 0 if not failures else 2
if __name__=='__main__':raise SystemExit(main())
