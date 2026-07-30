"""Frozen screening entrypoint.

The audit/attribution hard gate is intentionally checked before any candidate
implementation or run is permitted.  This protects the preregistration from
post-hoc candidate fishing.
"""
from common import *
def main():
 a=load(STAGE/'results/audit/attribution_gate.json')
 if not a['passed']:
  dump(STAGE/'results/screening/execution_summary.json',{'expected_runs':200,'completed_runs':0,'missing_runs':200,'status':'NOT_STARTED','reason':'ATTRIBUTION_GATE_HOLD'})
  print('SCREENING_NOT_STARTED: ATTRIBUTION_GATE_HOLD'); return 0
 raise RuntimeError('Screening runner is intentionally unavailable until a separately authorised attribution repair task passes the frozen gate.')
if __name__=='__main__':raise SystemExit(main())
