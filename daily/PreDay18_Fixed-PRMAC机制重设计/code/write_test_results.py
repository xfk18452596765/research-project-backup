from pathlib import Path
import subprocess,sys
from common import STAGE
r=subprocess.run([sys.executable,str(STAGE/'code/tests/test_redesign.py')],cwd=STAGE.parents[1],capture_output=True,text=True,encoding='utf8')
(STAGE/'logs').mkdir(exist_ok=True)
(STAGE/'logs/stage_tests.stdout.log').write_text(r.stdout,encoding='utf8')
(STAGE/'logs/stage_tests.stderr.log').write_text(r.stderr,encoding='utf8')
(STAGE/'test_results.txt').write_text('stage tests: '+('PASS' if r.returncode==0 else 'FAIL')+'\n'+r.stdout+r.stderr,encoding='utf8')
raise SystemExit(r.returncode)
