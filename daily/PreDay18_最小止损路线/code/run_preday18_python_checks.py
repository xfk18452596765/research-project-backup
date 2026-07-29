from __future__ import annotations
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for test in (ROOT/'tests/test_traffic_models.py',ROOT/'tests/test_preday18.py'):
    subprocess.run([sys.executable,str(test)],check=True)
print('PreDay18 Python checks passed')
