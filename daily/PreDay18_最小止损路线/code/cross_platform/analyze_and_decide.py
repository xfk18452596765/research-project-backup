from __future__ import annotations
import csv,json,math,sys
from collections import defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent; CODE=HERE.parent; ROOT=CODE.parent; sys.path.insert(0,str(CODE/'common'))
from result_io import read_json,write_json,write_csv
from statistics_utils import summary

def load_ns3():
    rows=[]
    for p in (ROOT/'results/ns3/raw').glob('ns3-*.json'):
        rows.append(read_json(p))
    return rows

def core_pairs(rows,platform):
    core=[r for r in rows if str(r['scenario_id']).startswith(platform+'-') and r.get('traffic_type') in ('periodic','poisson') and not any(x in str(r['scenario_id']) for x in ('hidden','control','M1','M2','burst'))]
    by={(r['traffic_type'],int(r['hop_count']),r['load_level'],int(r['seed']),r['protocol']):r for r in core}
    out=[]
    for traffic in ('periodic','poisson'):
      for hops in (2,4,6):
       for load in ('low','medium','high'):
        deltas=[];delivery=[]
        for seed in (7,17,27,37,47,57,67,77,87,97):
          a=by.get((traffic,hops,load,seed,'DCF'));b=by.get((traffic,hops,load,seed,'Fixed-PRMAC'))
          if a and b:deltas.append(float(b['average_end_to_end_delay'])-float(a['average_end_to_end_delay']));delivery.append(float(b['delivery_ratio'])-float(a['delivery_ratio']))
        if deltas: out.append({'platform':platform,'traffic_type':traffic,'hop_count':hops,'load_level':load,'n':len(deltas),'mean_delta_delay':sum(deltas)/len(deltas),'fixed_seed_wins':sum(x<0 for x in deltas),'mean_delta_delivery_ratio':sum(delivery)/len(delivery)})
    return out

def main():
    py=read_json(ROOT/'results/python/raw/python_core_raw.json'); ns=load_ns3(); ns_core=[r for r in ns if r['scenario_id'].startswith(('ns3-periodic','ns3-poisson'))]
    ns_sens=[r for r in ns if r not in ns_core]; pairs=core_pairs(ns,'ns3')
    write_csv(ROOT/'results/ns3/aggregate/ns3_core_paired.csv',pairs)
    py_pairs=list(csv.DictReader((ROOT/'results/python/aggregate/python_core_paired.csv').open(encoding='utf-8')))
    comparison=[]
    for traffic in ('periodic','poisson'):
      for hops,load in ((4,'medium'),(4,'high'),(6,'medium'),(6,'high')):
       p=next(x for x in py_pairs if x['traffic_type']==traffic and int(x['hop_count'])==hops and x['load_level']==load)
       n=next(x for x in pairs if x['traffic_type']==traffic and int(x['hop_count'])==hops and x['load_level']==load)
       pd=float(p['mean_delta_delay']);nd=float(n['mean_delta_delay']);comparison.append({'traffic_type':traffic,'hop_count':hops,'load_level':load,'python_direction':'better' if pd<0 else 'worse','ns3_direction':'better' if nd<0 else 'worse','consistent':(pd<0)==(nd<0),'python_delta_delay':pd,'ns3_delta_delay':nd,'interpretation':'trend-only; ns-3 is an application shim over AdhocWifiMac'})
    write_csv(ROOT/'results/cross_platform/python_ns3_core_comparison.csv',comparison)
    finite=all(all(not isinstance(v,float) or math.isfinite(v) for v in r.values()) for r in py+ns)
    active=sum(int(r.get('active_reservations_after_run',0)) for r in py+ns)
    targets={(4,'high'),(6,'medium'),(6,'high')}; keys={(4,'medium'),*targets}
    def select(rows,t):return [r for r in rows if r['traffic_type']==t and (int(r['hop_count']),r['load_level']) in targets]
    periodic=select(py_pairs,'periodic');poisson=select(py_pairs,'poisson')
    py_core_ok=all(float(x['mean_delta_delay'])<0 for x in periodic) and sum(float(x['bootstrap_ci95_high'])<0 for x in periodic)>=2 and all(float(x['mean_delta_delay'])<=0 for x in poisson) and sum(float(x['bootstrap_ci95_high'])<0 for x in poisson)>=2
    ns_periodic=select(pairs,'periodic');ns_poisson=select(pairs,'poisson');ns_core_ok=sum(float(x['mean_delta_delay'])<0 for x in ns_periodic)>=2 and sum(float(x['mean_delta_delay'])<0 for x in ns_poisson)>=2 and all(float(x['mean_delta_delivery_ratio'])>=-.02 for x in ns_periodic+ns_poisson)
    hard=len(py)==720 and len(ns_core)==360 and len(ns_sens)==160 and finite and active==0
    gaps=read_json(ROOT/'results/python/decision/python_sensitivity_capability_gaps.json'); robustness_ok=not gaps
    trend_ok=sum(bool(x['consistent']) for x in comparison)>=6
    ns3_delivery_hard_fail=any(float(x['mean_delta_delivery_ratio'])<-.02 for x in ns_periodic+ns_poisson)
    ns3_persistent_worse=sum(float(x['mean_delta_delay'])>0 for x in ns_periodic+ns_poisson)>=4
    decision='FAIL' if (not finite or active!=0 or ns3_delivery_hard_fail or ns3_persistent_worse) else ('PASS' if hard and py_core_ok and robustness_ok and ns_core_ok and trend_ok else 'HOLD')
    payload={'decision':decision,'counts':{'python_core':len(py),'python_sensitivity':len(read_json(ROOT/'results/python/raw/python_sensitivity_raw.json')),'ns3_core':len(ns_core),'ns3_sensitivity':len(ns_sens)},'criteria':{'hard_integrity':hard,'python_core':py_core_ok,'python_robustness':robustness_ok,'ns3_core':ns_core_ok,'cross_platform_trend':trend_ok,'finite':finite,'active_reservations_zero':active==0,'ns3_delivery_hard_fail':ns3_delivery_hard_fail,'ns3_persistent_worse':ns3_persistent_worse},'capability_gaps':gaps,'day18_status':'LOCKED' if decision!='PASS' else 'UNSTARTED_MAY_OPEN_AFTER_MERGE'}
    write_json(ROOT/'results/cross_platform/python_ns3_trend_summary.json',{'comparison':comparison,'consistent_cells':sum(bool(x['consistent']) for x in comparison)})
    write_json(ROOT/'results/cross_platform/stop_loss_decision.json',payload);print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
