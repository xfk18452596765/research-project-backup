from __future__ import annotations
import json,math,subprocess,sys
from pathlib import Path
CODE=Path(__file__).resolve().parents[1]; ROOT=CODE.parent; REPO=ROOT.parents[1]
sys.path[:0]=[str(CODE/'common'),str(CODE/'python_experiments')]
from statistics_utils import jain,paired_bootstrap_ci,summary
from traffic_models import periodic,poisson,burst

def main():
    shared=json.loads((ROOT/'configs/shared_parameters.json').read_text(encoding='utf-8'))
    assert shared['k']==2 and shared['cw_initial']==15 and shared['retry_limit']==7
    assert periodic(3,.1)==[0,.1,.2]
    assert poisson(100,.02,7)==poisson(100,.02,7)!=poisson(100,.02,17)
    assert len(burst(200,.02))==200 and math.isclose(jain([1,1]),1)
    assert summary([1,2,3])['n']==3 and len(paired_bootstrap_ci([-1,-2,-3],samples=100))==2
    raw=json.loads((ROOT/'results/python/raw/python_core_raw.json').read_text(encoding='utf-8'))
    assert len(raw)==720 and all(r['active_reservations_after_run']==0 for r in raw if r['protocol']=='Fixed-PRMAC')
    required={'platform','protocol','scenario_id','traffic_type','hop_count','load_level','seed','packet_count','delivery_ratio','average_end_to_end_delay','p95_end_to_end_delay','throughput_bps','control_bytes_sent','total_bytes_sent','active_reservations_after_run','terminal_sessions','simulation_end_time'}
    assert all(required<=r.keys() for r in raw)
    assert not any('RL' in str(r.get('protocol','')) for r in raw)
    status=subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True,encoding='utf-8')
    paths=[line[3:].replace('\\','/') for line in status.splitlines()]
    assert paths and all(p.startswith('daily/PreDay18_最小止损路线/') for p in paths),paths
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()=='635a7dc38bc135c989baa86f2f856cfd669acca0'
    print('PreDay18 focused tests passed')
if __name__=='__main__':main()
