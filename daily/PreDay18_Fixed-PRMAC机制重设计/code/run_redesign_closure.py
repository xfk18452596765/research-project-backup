from __future__ import annotations
from common import *
def main():
 source=load(REPO/'daily/PreDay18_Fixed-PRMAC机制诊断/results/decision/root_cause_classification.json')
 fraction=source['diagnostic_loss_explained_fraction']; passed=fraction>=.70
 ranking=[{'rank':1,'category':'OTHER','share_of_excess_delay_or_throughput_loss':fraction,'evidence':'Historical diagnostic only quantifies 6.53%; root causes are mixed and include base MAC/link-model semantics.'},{'rank':2,'category':'OVERBROAD_RESERVATION_SCOPE','share_of_excess_delay_or_throughput_loss':None,'evidence':'Not separately quantified; cannot be claimed as a preregistered candidate target.'}]
 dump(STAGE/'results/attribution/attribution_matrix.json',{'source':'PreDay18_Fixed-PRMAC机制诊断/results/decision/root_cause_classification.json','source_sha256':sha(REPO/'daily/PreDay18_Fixed-PRMAC机制诊断/results/decision/root_cause_classification.json'),'classification':source['root_cause_classification'],'quantified_explained_fraction':fraction,'threshold':.70,'ranking':ranking})
 dump(STAGE/'results/audit/attribution_gate.json',{'passed':passed,'required_fraction':.70,'observed_fraction':fraction,'decision_if_failed':'REDESIGN_HOLD','reason':'Top-two permitted redesign targets cannot explain at least 70% of excess cost.'})
 start=load(STAGE/'results/audit/historical_evidence_start.json')['manifests']; end=[manifest(p) for p in HISTORICAL]
 comparison=[{'directory':x['directory'],'start_sha256':x['sha256'],'end_sha256':y['sha256'],'immutable':x['sha256']==y['sha256']} for x,y in zip(start,end)]
 dump(STAGE/'results/audit/historical_evidence_end.json',{'manifests':end}); dump(STAGE/'results/audit/historical_evidence_comparison.json',{'passed':all(x['immutable'] for x in comparison),'comparison':comparison})
 decision='REDESIGN_HOLD' if not passed else 'UNREACHABLE'
 decision_data={'decision':decision,'base_commit':'1782431497d4710e02fd8c97fd9de24ae30372a0','candidate_registry_sha256':sha(STAGE/'configs/candidate_registry.json'),'redesign_patch_sha256':None,'attribution_fraction':fraction,'single_factor_runs':0,'combination_runs':0,'sensitivity_runs':0,'missing_runs':200,'failed_runs':0,'failed_gates':['ATTRIBUTION_TOP_TWO_EXPLAIN_70_PERCENT'],'Day18_status':'LOCKED','RL_started':False,'selected_candidate':None,'next_step':'Only a separately authorised minimal attribution-validation task; no candidate implementation is allowed in this stage.'}
 dump(STAGE/'results/decision/redesign_decision.json',decision_data)
 report=f'''# Fixed-PRMAC mechanism redesign readiness conclusion\n\n- base commit: `1782431497d4710e02fd8c97fd9de24ae30372a0`\n- semantic baseline: verified `BASELINE_READY`\n- candidate registry SHA256: `{decision_data['candidate_registry_sha256']}`\n- redesign patch SHA256: not created (blocked before implementation)\n- attribution conclusion: mixed root cause; quantified explanation {fraction:.2%}, below the required 70%\n- C1/C2/C3 single-factor runs: 0/200 (not started by hard gate)\n- combined candidates, sensitivity smoke: not started\n- decision: **{decision}**\n- Day18: **LOCKED**; RL started: **NO**\n\nThe historical evidence is immutable. This task did not rerun a complete stop-loss retest, did not start Day18, and did not run RL. The frozen policy forbids implementing candidates when their two target categories cannot explain 70% of excess cost; therefore no ns-3 redesign patch, candidate execution, combination, or smoke evidence is claimed.\n'''
 (STAGE/'docs/07_重设计就绪结论.md').write_text(report,encoding='utf8')
 print(decision)
if __name__=='__main__':main()
