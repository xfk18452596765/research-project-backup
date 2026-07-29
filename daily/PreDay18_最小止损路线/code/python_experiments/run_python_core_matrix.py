from __future__ import annotations
import argparse,json,math,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; CODE=HERE.parent
sys.path[:0]=[str(CODE/"common"),str(HERE)]
from legacy_adapters import dcf,fixed
from traffic_models import periodic,poisson
from result_io import write_csv,write_json
from statistics_utils import summary,paired_bootstrap_ci

ROOT=CODE.parent; CFG=ROOT/"configs"; RESULTS=ROOT/"results"/"python"

def enrich(row,*,traffic,load,arrivals,scenario):
    row.update({"platform":"python","scenario_id":scenario,"traffic_type":traffic,"topology_type":"chain",
      "load_level":load,"flow_count":1,"arrival_schedule":arrivals})
    row.setdefault("p50_end_to_end_delay",row["average_end_to_end_delay"])
    row.setdefault("maximum_queue_length",row.get("maximum_segment_queue_length",0))
    row.setdefault("average_queue_delay",row.get("average_segment_queue_delay",0.0))
    row.setdefault("maximum_queue_delay",row.get("maximum_segment_queue_delay",0.0))
    row.setdefault("simulation_end_time",row.get("measurement_end_time",0.0))
    return row

def aggregate(rows):
    metrics=["average_end_to_end_delay","p95_end_to_end_delay","delivery_ratio","throughput_bps","control_bytes_sent","total_bytes_sent"]
    groups={}
    for r in rows: groups.setdefault((r["traffic_type"],r["hop_count"],r["load_level"],r["protocol"]),[]).append(r)
    out=[]
    for key,group in sorted(groups.items()):
        item={"traffic_type":key[0],"hop_count":key[1],"load_level":key[2],"protocol":key[3]}
        for m in metrics:
            for k,v in summary([float(x[m]) for x in group]).items(): item[f"{m}_{k}"]=v
        out.append(item)
    return out

def paired(rows):
    by={}
    for r in rows: by[(r["traffic_type"],r["hop_count"],r["load_level"],r["seed"],r["protocol"])]=r
    out=[]
    for traffic in ("periodic","poisson"):
      for hops in (2,4,6):
       for load in ("low","medium","high"):
        ds=[]
        seeds=[seed for seed in SEEDS if (traffic,hops,load,seed,"DCF") in by and (traffic,hops,load,seed,"Fixed-PRMAC") in by]
        for seed in seeds:
            a=by[(traffic,hops,load,seed,"DCF")]; b=by[(traffic,hops,load,seed,"Fixed-PRMAC")]
            ds.append(float(b["average_end_to_end_delay"])-float(a["average_end_to_end_delay"]))
        lo,hi=paired_bootstrap_ci(ds)
        out.append({"traffic_type":traffic,"hop_count":hops,"load_level":load,"n":len(ds),"mean_delta_delay":sum(ds)/len(ds),
          "fixed_seed_wins":sum(d<0 for d in ds),"bootstrap_ci95_low":lo,"bootstrap_ci95_high":hi})
    return out

SEEDS=(7,17,27,37,47,57,67,77,87,97,107,117,127,137,147,157,167,177,187,197)
LOADS={"low":.05,"medium":.02,"high":.008}

def regression():
    legacy=next(ROOT.parents[1].glob("daily/Day13_*"))/"code"
    sys.path.insert(0,str(legacy)); from stop_loss_experiment import run_dcf_comparison_case,run_fixed_periodic_chain_case
    checks=[]
    for hops in (2,4,6):
      for load,mean in LOADS.items():
       for seed in (7,17,27):
        arrivals=periodic(8,mean)
        new_d=dcf(hops,arrivals,seed); old_d=run_dcf_comparison_case(hops,packet_count=8,interarrival_time=mean,seed=seed)
        new_f=fixed(hops,arrivals,seed); _,old_f=run_fixed_periodic_chain_case(hops,packet_count=8,interarrival_time=mean,seed=seed)
        for protocol,new,old in (("DCF",new_d,old_d),("Fixed-PRMAC",new_f,old_f)):
            ok=math.isclose(float(new["average_end_to_end_delay"]),float(old["average_end_to_end_delay"]),abs_tol=1e-12)
            checks.append({"protocol":protocol,"hops":hops,"load":load,"seed":seed,"match":ok})
    if not all(x["match"] for x in checks): raise RuntimeError("Day13 periodic wrapper regression mismatch")
    write_json(RESULTS/"decision"/"periodic_wrapper_regression.json",checks)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--packets",type=int,default=200); ap.add_argument("--limit-seeds",type=int,default=20); args=ap.parse_args()
    regression(); rows=[]; schedule_dir=RESULTS/"raw"/"arrival_schedules"
    for traffic in ("periodic","poisson"):
      for hops in (2,4,6):
       for load,mean in LOADS.items():
        for seed in SEEDS[:args.limit_seeds]:
            arrivals=periodic(args.packets,mean) if traffic=="periodic" else poisson(args.packets,mean,seed)
            schedule={"traffic":traffic,"hops":hops,"load":load,"seed":seed,"arrivals":arrivals}
            write_json(schedule_dir/f"{traffic}-{hops}hop-{load}-seed-{seed}.json",schedule)
            for protocol,runner,suffix in (("DCF",dcf,"dcf"),("Fixed-PRMAC",fixed,"fixed")):
                sid=f"python-{traffic}-{hops}hop-{load}-seed-{seed}-{suffix}"
                rows.append(enrich(runner(hops,arrivals,seed),traffic=traffic,load=load,arrivals=arrivals,scenario=sid))
    write_json(RESULTS/"raw"/"python_core_raw.json",rows); write_csv(RESULTS/"raw"/"python_core_raw.csv",rows)
    write_csv(RESULTS/"aggregate"/"python_core_aggregate.csv",aggregate(rows))
    pairs=paired(rows); write_csv(RESULTS/"aggregate"/"python_core_paired.csv",pairs); write_json(RESULTS/"decision"/"python_core_summary.json",{"runs":len(rows),"paired":pairs})
    print(f"python core runs: {len(rows)}")
if __name__=="__main__": main()
