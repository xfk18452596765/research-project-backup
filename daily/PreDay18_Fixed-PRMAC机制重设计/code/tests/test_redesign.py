import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_audit_and_hold():
 assert subprocess.run([sys.executable,str(ROOT/'code/run_redesign_audit.py')],cwd=ROOT.parents[1]).returncode==0
 assert subprocess.run([sys.executable,str(ROOT/'code/run_redesign_closure.py')],cwd=ROOT.parents[1]).returncode==0
 assert subprocess.run([sys.executable,str(ROOT/'code/run_redesign_screening.py')],cwd=ROOT.parents[1]).returncode==0
if __name__=='__main__':
 test_audit_and_hold(); print('1/1 PASS')
