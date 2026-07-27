"""Focused tests for Day13 complete Fixed-PRMAC and stop-loss checkpoint."""
from __future__ import annotations
import math
import sys
from pathlib import Path
CURRENT_DIR=Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path: sys.path.insert(0,str(CURRENT_DIR))
from fixed_prmac_end_to_end import Day13FixedPRMACConfig, EndToEndSegmentStatus, EndToEndStatus, FixedPRMACEndToEndController
from fixed_prmac_messages import ReservationStatus
from packet import Packet, PacketStatus
from simulator import Simulator
from stop_loss_experiment import HOP_COUNTS, LOAD_PROFILES, PACKETS_PER_RUN, QUEUE_LIMIT, SEEDS, StopLossScope, build_chain_adjacency, build_fairness_check, evaluate_stop_loss, run_fixed_periodic_chain_case

def make_controller(hops:int,*,config:Day13FixedPRMACConfig|None=None,log=False):
    sim=Simulator();sim.log_enabled=log
    ctl=FixedPRMACEndToEndController(simulator=sim,config=config,adjacency=build_chain_adjacency(hops))
    return sim,ctl

def run_single(hops:int,*,packet_id=2000,config=None):
    sim,ctl=make_controller(hops,config=config)
    p=Packet(packet_id,0,hops,0.0,route=tuple(range(hops+1)))
    sid=ctl.schedule_end_to_end(p,flow_id=f'test-{hops}')
    sim.run();return sim,ctl,p,ctl.end_to_end_records[sid]

def test_day13_defaults_preserve_fixed_design_and_dcf_fairness():
    cfg=Day13FixedPRMACConfig(); fair=build_fairness_check(StopLossScope())
    assert cfg.fixed_k==2 and cfg.fixed_cw_min==15
    assert cfg.initial_access_enabled and cfg.queue_limit==QUEUE_LIMIT==200
    assert fair['all_passed'] and fair['checks']['same_queue_limit']

def test_two_hop_route_delivers_in_one_segment():
    _,ctl,p,r=run_single(2)
    assert r.status==EndToEndStatus.COMPLETED and p.status==PacketStatus.DELIVERED
    assert p.current_node==2 and len(r.segments)==1
    assert r.segments[0].effective_hops==2 and r.segments[0].status==EndToEndSegmentStatus.COMPLETED
    assert len(ctl.table.active_records)==0

def test_four_hop_route_uses_two_ordered_segments():
    _,ctl,p,r=run_single(4)
    assert p.status==PacketStatus.DELIVERED
    assert [s.segment_start_index for s in r.segments]==[0,2]
    assert [s.effective_hops for s in r.segments]==[2,2]
    assert all(s.status==EndToEndSegmentStatus.COMPLETED for s in r.segments)
    assert len({s.retry_id for s in r.segments})==2
    assert len({s.reservation_id for s in r.segments})==2
    assert len(ctl.table.active_records)==0

def test_six_hop_route_uses_three_segments_and_exact_frame_counts():
    _,ctl,p,r=run_single(6)
    m=ctl.metrics.summary(ctl.table)
    assert p.current_hop_index==6 and len(r.segments)==3
    assert [s.effective_hops for s in r.segments]==[2,2,2]
    assert m['data_frames_sent']==6 and m['h_ack_frames_sent']==6
    assert m['completed_segments']==3 and m['released_reservations']==3

def test_odd_route_truncates_last_segment_to_one_hop():
    _,_,p,r=run_single(5)
    assert p.status==PacketStatus.DELIVERED
    assert [s.effective_hops for s in r.segments]==[2,2,1]
    assert [s.segment_start_index for s in r.segments]==[0,2,4]

def test_final_delivery_boundary_is_last_h_ack_reception():
    _,ctl,p,r=run_single(2)
    complete=[x for x in ctl.trace if x.event=='SEGMENT_FORWARD_COMPLETE'][-1]
    assert p.delivered_at is not None
    assert math.isclose(p.delivered_at,complete.time,abs_tol=1e-15)
    assert math.isclose(r.completed_at,complete.time,abs_tol=1e-15)

def test_release_completes_before_next_segment_access():
    _,ctl,_,r=run_single(4)
    first,second=r.segments
    assert first.released_at is not None
    assert second.scheduled_at==first.released_at
    events=[x.event for x in ctl.end_to_end_trace]
    assert events.index('SEGMENT_RELEASE_COMPLETE') < events.index('SEGMENT_ACCESS_BACKOFF',events.index('SEGMENT_RELEASE_COMPLETE')+1)

def test_conflict_then_release_allows_segment_retry_and_delivery():
    sim=Simulator();sim.log_enabled=False
    adj={0:{1},1:{0,2},2:{1,3},3:{2,4},4:{3}}
    ctl=FixedPRMACEndToEndController(simulator=sim,adjacency=adj)
    blocker=Packet(2100,2,4,0.0,route=(2,3,4))
    blocker_id=ctl.schedule_reservation(blocker,flow_id='blocker')
    sim.run(until=0.001)
    assert ctl.table.get(blocker_id).status==ReservationStatus.ACTIVE
    p=Packet(2101,0,2,sim.now,route=(0,1,2))
    sid=ctl.schedule_end_to_end(p,flow_id='candidate',at=sim.now)
    ctl.schedule_release(blocker_id,at=0.002)
    sim.run();r=ctl.end_to_end_records[sid]
    assert r.status==EndToEndStatus.COMPLETED and p.status==PacketStatus.DELIVERED
    assert r.segments[0].retries_used==1
    retry=ctl.retry_records[r.segments[0].retry_id]
    assert [a.status for a in retry.attempts]==[ReservationStatus.REJECTED,ReservationStatus.ACTIVE]

def test_persistent_conflict_exhausts_segment_and_fails_end_to_end():
    cfg=Day13FixedPRMACConfig(retry_limit=1,reservation_duration=1.0,random_seed=7)
    sim=Simulator();sim.log_enabled=False
    adj={0:{1},1:{0,2},2:{1,3},3:{2,4},4:{3}}
    ctl=FixedPRMACEndToEndController(simulator=sim,config=cfg,adjacency=adj)
    blocker=Packet(2200,2,4,0.0,route=(2,3,4));ctl.schedule_reservation(blocker,flow_id='blocker')
    sim.run(until=0.001)
    p=Packet(2201,0,2,sim.now,route=(0,1,2));sid=ctl.schedule_end_to_end(p,flow_id='failed',at=sim.now)
    sim.run();r=ctl.end_to_end_records[sid]
    assert r.status==EndToEndStatus.FAILED and p.status==PacketStatus.DROPPED
    assert r.segments[0].status==EndToEndSegmentStatus.FAILED
    assert 'retry_limit_exhausted' in r.failure_reason

def test_periodic_fixed_case_is_seed_reproducible_and_terminal():
    case1,row1=run_fixed_periodic_chain_case(4,packet_count=4,interarrival_time=0.05,seed=17)
    case2,row2=run_fixed_periodic_chain_case(4,packet_count=4,interarrival_time=0.05,seed=17)
    keys=('average_end_to_end_delay','p95_end_to_end_delay','delivery_ratio','retransmissions','total_bytes_sent')
    assert all(row1[k]==row2[k] for k in keys)
    assert row1['terminal_sessions']==row1['created_packets']
    assert row1['active_reservations_after_run']==0
    assert all(p.status in {PacketStatus.DELIVERED,PacketStatus.DROPPED} for p in case1.packets)


def test_same_node_high_load_waits_in_fifo_without_local_pr_nack():
    case,row=run_fixed_periodic_chain_case(2,packet_count=4,interarrival_time=0.008,seed=7)
    metrics=case.controller.metrics.summary(case.controller.table)
    assert row['delivery_ratio']==1.0 and row['dropped_packets']==0
    assert metrics['rejected_reservations']==0
    assert metrics['reservation_retries_scheduled']==0
    assert metrics['maximum_segment_queue_length']>=2
    assert metrics['average_segment_queue_delay']>0.0
    assert case.controller.segment_queue_snapshot()=={}
    assert case.controller._active_segment_by_node=={}

def test_segment_queue_delay_is_included_without_counting_as_retry():
    case,row=run_fixed_periodic_chain_case(4,packet_count=4,interarrival_time=0.008,seed=17)
    metrics=case.controller.metrics.summary(case.controller.table)
    later=case.controller.end_to_end_records[next(reversed(case.controller.end_to_end_records))]
    assert any(segment.queue_delay>0.0 for segment in later.segments)
    assert metrics['total_segment_queue_delay']>0.0
    assert row['delivery_ratio']==1.0
    assert row['queue_overflow_drops']==0

def test_queue_limit_counts_active_head_and_drops_only_excess_packet():
    cfg=Day13FixedPRMACConfig(queue_limit=1,random_seed=7)
    sim,ctl=make_controller(2,config=cfg)
    p1=Packet(2300,0,2,0.0,route=(0,1,2))
    p2=Packet(2301,0,2,0.0,route=(0,1,2))
    sid1=ctl.schedule_end_to_end(p1,flow_id='queue-limit',at=0.0)
    sid2=ctl.schedule_end_to_end(p2,flow_id='queue-limit',at=0.0)
    sim.run()
    r1=ctl.end_to_end_records[sid1];r2=ctl.end_to_end_records[sid2]
    metrics=ctl.metrics.summary(ctl.table)
    assert r1.status==EndToEndStatus.COMPLETED and p1.status==PacketStatus.DELIVERED
    assert r2.status==EndToEndStatus.FAILED and p2.status==PacketStatus.DROPPED
    assert 'segment_queue_overflow' in r2.failure_reason
    assert metrics['queue_overflow_drops']==1
    assert metrics['maximum_segment_queue_length']==1
    assert ctl.segment_queue_snapshot()=={}

def test_stop_loss_scope_remains_2_4_6_three_loads_three_seeds():
    assert HOP_COUNTS==(2,4,6) and SEEDS==(7,17,27) and PACKETS_PER_RUN==8 and QUEUE_LIMIT==200
    assert [(p.name,p.interarrival_time) for p in LOAD_PROFILES]==[('low',0.05),('medium',0.02),('high',0.008)]

def _synthetic_rows(fixed_better:bool=True):
    raw=[];agg=[];comp=[]
    for protocol in ('DCF','Fixed-PRMAC'):
        for h in (2,4,6):
            for load in ('low','medium','high'):
                delay=float(h)*(2.0 if protocol=='DCF' else (1.5 if fixed_better else 2.5))
                agg.append({'protocol':protocol,'hop_count':h,'load_level':load,'mean_average_end_to_end_delay':delay})
                for seed in (7,17,27):
                    raw.append({'protocol':protocol,'hop_count':h,'load_level':load,'seed':seed,'average_end_to_end_delay':delay,'terminal_sessions':8,'created_packets':8,'active_reservations_after_run':0})
    for h in (2,4,6):
        for load in ('low','medium','high'):
            comp.append({'hop_count':h,'load_level':load,'fixed_delay_lower':int(fixed_better),'fixed_delivery_not_lower':1})
    return raw,agg,comp

def test_stop_loss_evaluator_never_passes_unfair_or_worse_evidence():
    raw,agg,comp=_synthetic_rows(False)
    result=evaluate_stop_loss(raw_rows=raw,aggregate_rows=agg,comparison_rows=comp,fairness={'all_passed':False})
    assert result['decision']=='FAIL'

def test_stop_loss_evaluator_can_pass_consistent_fair_evidence_without_percent_threshold():
    raw,agg,comp=_synthetic_rows(True)
    result=evaluate_stop_loss(raw_rows=raw,aggregate_rows=agg,comparison_rows=comp,fairness={'all_passed':True})
    assert result['decision']=='PASS'


def _target_scope_rows_with_only_three_global_wins():
    """Build evidence matching the declared core target without 9-cell majority."""
    core={(4,'high'),(6,'medium'),(6,'high')}
    raw=[];agg=[];comp=[]
    for h in (2,4,6):
        for load in ('low','medium','high'):
            dcf_delay=float(h)*10.0
            fixed_wins=(h,load) in core
            fixed_delay=dcf_delay-2.0 if fixed_wins else dcf_delay+1.0
            agg.append({'protocol':'DCF','hop_count':h,'load_level':load,'mean_average_end_to_end_delay':dcf_delay})
            agg.append({'protocol':'Fixed-PRMAC','hop_count':h,'load_level':load,'mean_average_end_to_end_delay':fixed_delay})
            comp.append({'hop_count':h,'load_level':load,'fixed_delay_lower':int(fixed_wins),'fixed_delivery_not_lower':1})
            for seed in (7,17,27):
                raw.append({'protocol':'DCF','hop_count':h,'load_level':load,'seed':seed,'average_end_to_end_delay':dcf_delay,'terminal_sessions':8,'created_packets':8,'active_reservations_after_run':0,'queue_overflow_drops':0})
                raw.append({'protocol':'Fixed-PRMAC','hop_count':h,'load_level':load,'seed':seed,'average_end_to_end_delay':fixed_delay,'terminal_sessions':8,'created_packets':8,'active_reservations_after_run':0,'queue_overflow_drops':0})
    return raw,agg,comp

def test_stop_loss_gate_matches_declared_long_congested_target_not_global_majority():
    raw,agg,comp=_target_scope_rows_with_only_three_global_wins()
    result=evaluate_stop_loss(raw_rows=raw,aggregate_rows=agg,comparison_rows=comp,fairness={'all_passed':True})
    assert result['decision']=='PASS'
    assert result['criteria']['core_target_cells_all_win']
    assert result['criteria']['fixed_delay_wins_at_least_3_of_4_critical_cells']
    assert not result['observations']['fixed_delay_wins_majority_of_9_cells']
    assert not result['observations']['global_9_cell_majority_is_required_gate']

def test_stop_loss_requires_no_delivery_loss_across_all_nine_cells():
    raw,agg,comp=_target_scope_rows_with_only_three_global_wins()
    comp[0]['fixed_delivery_not_lower']=0
    result=evaluate_stop_loss(raw_rows=raw,aggregate_rows=agg,comparison_rows=comp,fairness={'all_passed':True})
    assert result['decision']=='HOLD'
    assert not result['criteria']['no_delivery_ratio_loss_in_any_of_9_cells']

def run_all_tests():
    tests=[
        test_day13_defaults_preserve_fixed_design_and_dcf_fairness,
        test_two_hop_route_delivers_in_one_segment,
        test_four_hop_route_uses_two_ordered_segments,
        test_six_hop_route_uses_three_segments_and_exact_frame_counts,
        test_odd_route_truncates_last_segment_to_one_hop,
        test_final_delivery_boundary_is_last_h_ack_reception,
        test_release_completes_before_next_segment_access,
        test_conflict_then_release_allows_segment_retry_and_delivery,
        test_persistent_conflict_exhausts_segment_and_fails_end_to_end,
        test_periodic_fixed_case_is_seed_reproducible_and_terminal,
        test_same_node_high_load_waits_in_fifo_without_local_pr_nack,
        test_segment_queue_delay_is_included_without_counting_as_retry,
        test_queue_limit_counts_active_head_and_drops_only_excess_packet,
        test_stop_loss_scope_remains_2_4_6_three_loads_three_seeds,
        test_stop_loss_evaluator_never_passes_unfair_or_worse_evidence,
        test_stop_loss_evaluator_can_pass_consistent_fair_evidence_without_percent_threshold,
        test_stop_loss_gate_matches_declared_long_congested_target_not_global_majority,
        test_stop_loss_requires_no_delivery_loss_across_all_nine_cells,
    ]
    for test in tests:
        test();print(f'[PASS] {test.__name__}')
    print('\nAll Day13 Fixed-PRMAC validation and stop-loss tests passed.')
if __name__=='__main__':run_all_tests()
