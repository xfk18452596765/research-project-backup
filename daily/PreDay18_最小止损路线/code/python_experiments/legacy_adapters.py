"""Arrival-schedule adapters around the frozen Day08 and Day13 implementations."""
from __future__ import annotations
import random,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]; DAILY=ROOT/"daily"
def _code(day:str)->Path: return next(DAILY.glob(day+"_*"))/"code"
for day in ("Day13","Day12","Day11","Day10","Day09","Day08","Day07","Day06","Day05","Day04","Day03"):
    p=str(_code(day))
    while p in sys.path: sys.path.remove(p)
    sys.path.insert(0,p)

from simulator import Simulator
from node import Node
from packet import Packet,PacketStatus
from dcf_config import DCFConfig
from dcf_validation import (CollisionChannel,DCFValidationMetricsCollector,DCFContentionCoordinator,
 DCFMultiHopNetwork,DCFValidatedMultiHopMac,PeriodicChainCase,summarize_periodic_case)
from stop_loss_experiment import build_chain_adjacency,summarize_fixed_case,FixedPeriodicCase
from fixed_prmac_end_to_end import Day13FixedPRMACConfig,FixedPRMACEndToEndController

def dcf(hops:int, arrivals:list[float], seed:int, payload:int=1024)->dict:
    started=time.perf_counter(); sim=Simulator(); sim.log_enabled=False; channel=CollisionChannel()
    cfg=DCFConfig(retry_limit=7); metrics=DCFValidationMetricsCollector(slot_time=cfg.slot_time)
    coord=DCFContentionCoordinator(sim,channel,cfg); network=DCFMultiHopNetwork(simulator=sim,metrics=metrics)
    nodes=[Node(node_id=i,queue_limit=200) for i in range(hops+1)]; macs=[]
    for sender in range(hops):
        nodes[sender].neighbors.add(sender+1)
        macs.append(DCFValidatedMultiHopMac(simulator=sim,node=nodes[sender],channel=channel,metrics=metrics,
          config=cfg,rng=random.Random(seed+1009*sender),coordinator=coord,network=network))
    route=tuple(range(hops+1)); packets=[]
    for i,at in enumerate(arrivals):
        p=Packet(packet_id=8_000_000+seed*1000+hops*100+i,source=0,destination=hops,created_at=at,size_bytes=payload,route=route)
        packets.append(p); network.schedule_source_packet(p,at=at)
    case=PeriodicChainCase(sim,channel,cfg,metrics,coord,network,nodes,macs,packets,hops,len(packets),
      (arrivals[-1]/(len(arrivals)-1) if len(arrivals)>1 else 0.0),seed)
    sim.run(); metrics.capture_coordinator(coord); base=summarize_periodic_case(case)
    delivered=[p for p in packets if p.status==PacketStatus.DELIVERED and p.end_to_end_delay is not None]
    delays=[float(p.end_to_end_delay) for p in delivered]; successful=int(base["successful_hops"])
    attempts=successful+int(base["collided_packet_attempts"]); data_bytes=attempts*(34+payload); ack_bytes=successful*14
    return _schema("DCF",hops,seed,packets,delays,sim.now,base,0,ack_bytes,attempts,data_bytes,successful,time.perf_counter()-started)

def fixed(hops:int, arrivals:list[float], seed:int, payload:int=1024)->dict:
    started=time.perf_counter(); sim=Simulator(); sim.log_enabled=False
    ctl=FixedPRMACEndToEndController(simulator=sim,config=Day13FixedPRMACConfig(retry_limit=7,random_seed=seed,queue_limit=200),adjacency=build_chain_adjacency(hops))
    packets=[]; route=tuple(range(hops+1))
    for i,at in enumerate(arrivals):
        p=Packet(packet_id=13_000_000+seed*1000+hops*100+i,source=0,destination=hops,created_at=at,size_bytes=payload,route=route)
        packets.append(p); ctl.schedule_end_to_end(p,flow_id=f"fixed-{hops}",at=at)
    sim.run(); case=FixedPeriodicCase(sim,ctl,packets,hops,len(packets),(arrivals[-1]/(len(arrivals)-1) if len(arrivals)>1 else 0.0),seed)
    row=summarize_fixed_case(case); row["wall_clock_runtime"]=time.perf_counter()-started
    return row

def _schema(protocol,hops,seed,packets,delays,end,base,active,control_bytes,data_frames,data_bytes,ack_frames,wall):
    from statistics_utils import percentile
    delivered=len(delays); created=len(packets); total_frames=data_frames+ack_frames; total_bytes=data_bytes+control_bytes
    return {"protocol":protocol,"hop_count":hops,"packet_count":created,"seed":seed,"measurement_end_time":float(end),
     "created_packets":created,"delivered_packets":delivered,"dropped_packets":created-delivered,"delivery_ratio":delivered/created,
     "average_end_to_end_delay":sum(delays)/delivered if delivered else 0.0,"p50_end_to_end_delay":percentile(delays,.5),
     "p95_end_to_end_delay":percentile(delays,.95),"p99_end_to_end_delay":percentile(delays,.99),"maximum_end_to_end_delay":max(delays,default=0),
     "throughput_bps":delivered*1024*8/end if end else 0,"retransmissions":int(base["retransmissions"]),
     "collision_or_conflict_events":int(base["shared_collision_events"]),"contention_attempts":int(base["competition_attempts"]),
     "control_frames_sent":ack_frames,"control_bytes_sent":control_bytes,"data_frames_sent":data_frames,"data_bytes_sent":data_bytes,
     "total_frames_sent":total_frames,"total_bytes_sent":total_bytes,"queue_overflow_drops":0,"maximum_queue_length":0,
     "average_queue_delay":float(base["average_queue_delay"]),"maximum_queue_delay":0.0,"active_reservations_after_run":active,
     "terminal_sessions":created,"simulation_end_time":float(end),"wall_clock_runtime":wall}
