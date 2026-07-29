from __future__ import annotations
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; CODE=HERE.parent; sys.path[:0]=[str(CODE/'common'),str(HERE)]
from traffic_models import periodic,poisson,burst
from legacy_adapters import dcf,fixed
from multiflow_adapters import run_flows
from result_io import write_json,write_csv

ROOT=CODE.parent; OUT=ROOT/'results/python'; SEEDS=(7,17,27,37,47,57,67,77,87,97,107,117,127,137,147,157,167,177,187,197)

def tagged(row,kind,scenario,seed,load):
    row.update({'platform':'python','sensitivity_type':kind,'scenario_id':scenario,'seed':seed,'load_level':load})
    return row

def main():
    rows=[]
    for hops,load,mean in ((4,'medium',.02),(4,'high',.008),(6,'medium',.02),(6,'high',.008)):
      for seed in SEEDS:
       arr=burst(200,mean)
       for proto,fn in (('DCF',dcf),('Fixed-PRMAC',fixed)):
        rows.append(tagged(fn(hops,arr,seed),'burst',f'python-burst-{hops}hop-{load}-seed-{seed}-{proto}',seed,load))
    scenarios={'M1':((0,1,2,3,4,5,6),(1,2,3,4,5,6)),'M2':((0,1,2,3,4,5,6),(6,5,4,3,2,1,0)),'M3':((0,1,2,3,4),(2,3,4,5,6))}
    for name,routes in scenarios.items():
      for load,mean in (('medium',.02),('high',.008)):
       for seed in SEEDS[:10]:
        schedules=[periodic(100,mean),periodic(100,mean)]
        for proto in ('DCF','Fixed-PRMAC'):
         rows.append(tagged(run_flows(proto,list(routes),schedules,seed),'multiflow',f'python-{name}-{load}-seed-{seed}-{proto}',seed,load)|{'multiflow_scenario':name})
    routes=[(0,1,2),(4,5,6)]
    for seed in SEEDS:
      schedules=[periodic(100,.02),periodic(100,.02)]
      for proto in ('DCF','Fixed-PRMAC'):
       rows.append(tagged(run_flows(proto,routes,schedules,seed),'spatial_reuse',f'python-spatial-seed-{seed}-{proto}',seed,'medium'))
    for traffic in ('periodic','poisson'):
      for seed in SEEDS[:10]:
       arr=periodic(200,.008) if traffic=='periodic' else poisson(200,.008,seed)
       for proto,fn in (('DCF',dcf),('Fixed-PRMAC',fixed)):
        rows.append(tagged(fn(8,arr,seed),'eight_hop',f'python-8hop-{traffic}-seed-{seed}-{proto}',seed,'high')|{'traffic_type':traffic})
    gaps=[
      {'scenario':'control_loss','status':'NOT_RUN','reason':'Frozen Day08/Day13 APIs expose no frame-loss hook; injecting at receive callbacks without new timeouts can deadlock and would change protocol semantics.'},
      {'scenario':'hidden_terminal','status':'NOT_VALID','reason':'Frozen Python CollisionChannel is global and has no separate carrier-sense/interference matrices; a claimed hidden-terminal result would be fabricated.'}
    ]
    write_json(OUT/'raw/python_sensitivity_raw.json',rows); write_csv(OUT/'raw/python_sensitivity_raw.csv',rows)
    write_json(OUT/'decision/python_sensitivity_capability_gaps.json',gaps)
    print(f'python sensitivity runs: {len(rows)}; capability gaps: {len(gaps)}')
if __name__=='__main__': main()
