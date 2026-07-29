from __future__ import annotations
import subprocess,sys
from pathlib import Path
CODE=Path(__file__).resolve().parent; REPO=CODE.parents[2]
steps=[CODE/'run_preday18_python_checks.py',CODE/'run_preday18_ns3_checks.py',CODE/'cross_platform/analyze_and_decide.py']
with (CODE.parent/'logs/full_closure.log').open('w',encoding='utf-8') as log:
    for step in steps:
        p=subprocess.run([sys.executable,str(step)],cwd=REPO,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        log.write(p.stdout);print(p.stdout,end='');p.check_returncode()
    reg=next((REPO/'daily').glob('Day17_*'))/'code/run_day03_day17_regression.py'
    p=subprocess.run([sys.executable,str(reg)],cwd=REPO,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log.write(p.stdout);print(p.stdout,end='');p.check_returncode()
print('PreDay18 full closure passed')
