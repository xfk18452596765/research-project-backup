from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; raw=ROOT/'results/ns3/raw'
rows=[json.loads(p.read_text(encoding='utf-8')) for p in raw.glob('ns3-*.json')]
assert len(rows)==520,len(rows)
required={'platform','ns3_version','implementation_type','protocol','scenario_id','traffic_type','hop_count','load_level','seed','created_packets','delivered_packets','delivery_ratio','average_end_to_end_delay','active_reservations_after_run','exit_code'}
assert all(required<=r.keys() for r in rows)
assert all(r['exit_code']==0 and r['active_reservations_after_run']==0 for r in rows)
assert all(r['ns3_version']=='3.43' for r in rows)
print('PreDay18 ns-3 result checks passed: 520 runs')
