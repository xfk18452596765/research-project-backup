#!/usr/bin/env python3
"""Execution record: incomplete MAC implementation is a HOLD, never a PASS."""
from pathlib import Path
import json
stage=Path(__file__).resolve().parents[1]
def main():
 out=stage/'results'/'decision'; out.mkdir(parents=True,exist_ok=True)
 r={'decision':'SEMANTIC_BASELINE_V2_HOLD','gate0':'PASS','gate1':'PASS: official ns-3.43 A/B acquired','gate2':'HOLD: patch A/B replay not completed','gate3':'HOLD: topology evidence not run','gate4':'HOLD: causal traces not run','gate5':'HOLD: Fixed-PRMAC V2 absent','gate6':'HOLD: no MAC access-path reservation extension','gate7':'HOLD: smoke matrix not run','blocker':'Fixed-PRMAC V2 local reservation must be implemented in a Wi-Fi MAC access component before evidence may be collected.'}
 (out/'build_and_gates.json').write_text(json.dumps(r,indent=2)+'\\n',encoding='utf-8'); print(json.dumps(r,indent=2))
if __name__=='__main__': main()
