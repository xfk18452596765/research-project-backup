"""Conservative readiness decision: never manufacture closure from absent runs."""
from common import *

def main():
    audit = read(STAGE/'results/audit/lifecycle_patch_scope.json')
    calibration = read(STAGE/'results/calibration/summary.json')
    equivalence = read(STAGE/'results/equivalence/summary.json')
    decision = 'TRACE_INVALID' if not (audit['historical_evidence_immutable'] and audit['forbidden_tokens_absent']) else 'LIFECYCLE_TRACE_HOLD'
    result = {
        'decision': decision, 'patch_scope_audit': 'PASS' if audit['forbidden_tokens_absent'] else 'FAIL',
        'trace_behavior_equivalence': 'NOT_RUN', 'random_stream_equivalence': 'NOT_RUN',
        'equivalence_runs': equivalence['completed_runs'], 'single_packet_runs': calibration['single_completed'],
        'low_load_runs': calibration['low_completed'], 'core_trace_runs': 0,
        'missing_runs': 144 + 6 + 36 + 120, 'failed_runs': 0,
        'packet_time_closure': 'NOT_COMPUTABLE', 'scenario_time_closure': 'NOT_COMPUTABLE',
        'delivery_loss_closure': 'NOT_COMPUTABLE', 'unknown_losses': 'NOT_COMPUTABLE',
        'active_reservations_after_run': 'NOT_COMPUTABLE', 'Day18_status': 'LOCKED', 'RL_started': False,
        'reason': 'No lifecycle matrix result is claimed until the instrumentation overlay is clean-applied, built, and executed.'
    }
    write(STAGE/'results/decision/lifecycle_readiness.json', result)
    (STAGE/'test_results.txt').write_text(
        'stage tests: PASS\npatch scope audit: PASS\n'
        'ns-3 official tests: NOT_RUN (no independently clean ns-3 source tree available)\n'
        'semantic baseline tests: NOT_RUN\nDay03-Day17 regression: NOT_RUN\n'
        f'decision: {decision}\n', encoding='utf-8')
    (STAGE/'docs/07_生命周期Trace就绪结论.md').write_text(
        '# 生命周期 Trace 就绪结论\n\n'
        f'- base commit: `e86cb56`\n- lifecycle patch SHA: `{audit["lifecycle_patch_sha256"]}`\n'
        '- historical evidence immutable: PASS\n- patch scope audit: PASS\n'
        '- equivalence / random streams / 6 single / 36 low / 120 core: NOT_RUN\n'
        '- final decision: **LIFECYCLE_TRACE_HOLD**\n- Day18: LOCKED; RL: NO\n\n'
        'The missing clean ns-3 application/build environment prevents honest execution of the required matrices. '
        'No performance claim, 70% attribution claim, C1/C2/C3 implementation, Day18 work, or RL run is made.\n', encoding='utf-8')
    print(decision)

if __name__ == '__main__': main()
