"""Multi-flow wrappers using the same frozen Day08/Day13 protocol classes."""
from __future__ import annotations
import random,time
from legacy_adapters import *
import legacy_adapters as legacy
from statistics_utils import percentile,jain

def run_flows(protocol:str,routes:list[tuple[int,...]],schedules:list[list[float]],seed:int,payload:int=1024)->dict:
    started=time.perf_counter(); max_node=max(max(r) for r in routes); packets=[]; flow_of={}
    if protocol=="DCF":
        sim=Simulator(); sim.log_enabled=False; channel=CollisionChannel(); cfg=DCFConfig(retry_limit=7)
        metrics=DCFValidationMetricsCollector(slot_time=cfg.slot_time); coord=DCFContentionCoordinator(sim,channel,cfg)
        network=DCFMultiHopNetwork(simulator=sim,metrics=metrics); nodes=[Node(node_id=i,queue_limit=200) for i in range(max_node+1)]; senders=set()
        for route in routes:
            for a,b in zip(route,route[1:]): nodes[a].neighbors.add(b); senders.add(a)
        macs=[DCFValidatedMultiHopMac(simulator=sim,node=nodes[s],channel=channel,metrics=metrics,config=cfg,rng=random.Random(seed+1009*s),coordinator=coord,network=network) for s in sorted(senders)]
        for flow,(route,arrivals) in enumerate(zip(routes,schedules)):
            for i,at in enumerate(arrivals):
                p=Packet(packet_id=20_000_000+seed*10000+flow*1000+i,source=route[0],destination=route[-1],created_at=at,size_bytes=payload,route=route)
                flow_of[p.packet_id]=flow; packets.append(p); network.schedule_source_packet(p,at=at)
        sim.run(); metrics.capture_coordinator(coord); base=summarize_periodic_case(PeriodicChainCase(sim,channel,cfg,metrics,coord,network,nodes,macs,packets,max(len(r)-1 for r in routes),len(packets),0.0,seed))
        successful=int(base["successful_hops"]); attempts=successful+int(base["collided_packet_attempts"])
        row=legacy._schema("DCF",max(len(r)-1 for r in routes),seed,packets,[float(p.end_to_end_delay) for p in packets if p.status==PacketStatus.DELIVERED and p.end_to_end_delay is not None],sim.now,base,0,successful*14,attempts,attempts*(34+payload),successful,time.perf_counter()-started)
    else:
        sim=Simulator(); sim.log_enabled=False; adjacency={i:set() for i in range(max_node+1)}
        for route in routes:
            for a,b in zip(route,route[1:]): adjacency[a].add(b); adjacency[b].add(a)
        ctl=FixedPRMACEndToEndController(simulator=sim,config=Day13FixedPRMACConfig(retry_limit=7,random_seed=seed,queue_limit=200),adjacency=adjacency)
        for flow,(route,arrivals) in enumerate(zip(routes,schedules)):
            for i,at in enumerate(arrivals):
                p=Packet(packet_id=30_000_000+seed*10000+flow*1000+i,source=route[0],destination=route[-1],created_at=at,size_bytes=payload,route=route)
                flow_of[p.packet_id]=flow; packets.append(p); ctl.schedule_end_to_end(p,flow_id=f"flow-{flow}",at=at)
        sim.run(); row=summarize_fixed_case(FixedPeriodicCase(sim,ctl,packets,max(len(r)-1 for r in routes),len(packets),0.0,seed)); row["wall_clock_runtime"]=time.perf_counter()-started
    per=[]
    for flow in range(len(routes)):
        ps=[p for p in packets if flow_of[p.packet_id]==flow]; ds=[float(p.end_to_end_delay) for p in ps if p.status==PacketStatus.DELIVERED and p.end_to_end_delay is not None]
        per.append({"flow_id":flow,"created":len(ps),"delivered":len(ds),"delivery_ratio":len(ds)/len(ps),"average_delay":sum(ds)/len(ds) if ds else 0.0,"p95_delay":percentile(ds,.95)})
    row["per_flow_metrics"]=per; row["flow_count"]=len(routes); row["jain_fairness"]=jain([x["delivery_ratio"] for x in per])
    return row
