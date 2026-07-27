"""Run the Day13 complete 6-hop Fixed-PRMAC delivery demonstration."""
from __future__ import annotations
import sys
from pathlib import Path
CURRENT_DIR=Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path: sys.path.insert(0,str(CURRENT_DIR))
from fixed_prmac_end_to_end import FixedPRMACEndToEndController
from packet import Packet
from simulator import Simulator
from stop_loss_experiment import build_chain_adjacency

def main()->None:
    results=CURRENT_DIR.parent/'results';results.mkdir(parents=True,exist_ok=True)
    simulator=Simulator();simulator.log_enabled=True
    controller=FixedPRMACEndToEndController(simulator=simulator,adjacency=build_chain_adjacency(6))
    packet=Packet(packet_id=1700,source=0,destination=6,created_at=0.0,size_bytes=1024,route=(0,1,2,3,4,5,6))
    session_id=controller.schedule_end_to_end(packet,flow_id='day13-six-hop-demo')
    simulator.run();record=controller.end_to_end_records[session_id]
    print('\n=== Day13 end-to-end orchestration trace ===')
    for item in controller.end_to_end_trace:
        print(f"{item.time:.9f}s | node={item.node_id} | {item.event:<28} | packet={item.packet_id} | segment={item.segment_number} | {item.detail}")
    print('\n=== End-to-end result ===')
    print(f'session_status          : {record.status.value}')
    print(f'packet_status           : {packet.status.value}')
    print(f'packet_current_node     : {packet.current_node}')
    print(f'packet_current_hop_index: {packet.current_hop_index}')
    print(f'segment_count           : {len(record.segments)}')
    print('segment_effective_hops  : '+', '.join(str(s.effective_hops) for s in record.segments))
    print(f'total_retries           : {record.total_retries}')
    print(f'end_to_end_delay        : {float(packet.end_to_end_delay or 0.0):.9f}s')
    print('\n=== Metrics ===')
    for key,value in controller.metrics.summary(controller.table).items(): print(f'{key:<40}: {value}')
    trace_path=controller.export_end_to_end_trace_csv(results/'fixed_prmac_end_to_end_trace.csv')
    summary_path=controller.export_end_to_end_summary_json(results/'fixed_prmac_end_to_end_summary.json')
    print('\nSaved:');print(f'- {trace_path}');print(f'- {summary_path}')
if __name__=='__main__':main()
