"""Run the Day13 DCF vs Fixed-PRMAC stop-loss pre-experiment."""
from __future__ import annotations
import sys
from pathlib import Path
CURRENT_DIR=Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path: sys.path.insert(0,str(CURRENT_DIR))
from stop_loss_experiment import run_stop_loss_matrix

def main()->None:
    results=CURRENT_DIR.parent/'results'
    payload=run_stop_loss_matrix(results)
    print('=== Day13 stop-loss comparison ===')
    for row in payload['comparison_rows']:
        print(
            f"{row['hop_count']} hops | {row['load_level']:<6} | "
            f"DCF={row['dcf_mean_delay']:.9f}s | Fixed={row['fixed_mean_delay']:.9f}s | "
            f"fixed_lower={bool(row['fixed_delay_lower'])} | "
            f"delivery_not_lower={bool(row['fixed_delivery_not_lower'])} | "
            f"fixed_queue_delay={row['fixed_mean_queue_delay']:.9f}s | "
            f"fixed_queue_drops={row['fixed_mean_queue_overflow_drops']:.3f}"
        )
    evaluation=payload['evaluation']
    print('\n=== STOP-LOSS DECISION ===')
    print(f"policy_version: {evaluation['policy_version']}")
    print(f"decision: {evaluation['decision']}")
    for key,value in evaluation['criteria'].items(): print(f'{key:<55}: {value}')
    print('--- descriptive observations (not PASS gates) ---')
    for key,value in evaluation['observations'].items(): print(f'{key:<55}: {value}')
    for key,value in evaluation['evidence_counts'].items(): print(f'{key:<55}: {value}')
    print(f"next_action: {evaluation['next_action']}")
    print('\nSaved:')
    for name in ('day13_stop_loss_raw.csv','day13_stop_loss_aggregate.csv','day13_stop_loss_comparison.csv','day13_stop_loss_decision.json'):
        print(f'- {results/name}')
if __name__=='__main__':main()
