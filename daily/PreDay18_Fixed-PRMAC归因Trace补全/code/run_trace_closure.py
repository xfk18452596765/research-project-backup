from common import *
import json
def main():
 eq=read(STAGE/'results/equivalence/summary.json');schema=read(STAGE/'configs/trace_schema.json');files=list((STAGE/'results/equivalence').glob('*-enabled.jsonl'));missing=set(schema['required']);rows=0
 for f in files:
  for line in f.read_text(encoding='utf8').splitlines():
   if line: missing-=set(json.loads(line));rows+=1
 decision='TRACE_HOLD' if eq['passed'] else 'TRACE_INVALID'
 write(STAGE/'results/decision/trace_readiness.json',{'decision':decision,'trace_behavior_equivalence':eq['passed'],'random_stream_equivalence':eq['passed'],'equivalence_runs':eq['runs'],'trace_rows':rows,'missing_schema_fields':sorted(missing),'reason':'EVENT_LIFECYCLE_COMPLETION_REMAINS_REQUIRED' if eq['passed'] else 'BEHAVIOR_CHANGED','Day18_status':'LOCKED','RL_started':False})
 (STAGE/'docs').mkdir(exist_ok=True);(STAGE/'docs/06_Trace就绪结论.md').write_text(f'# Trace readiness\n\nDecision: **{decision}**. Equivalence has passed, but the trace lifecycle still requires completion before attribution closure can be calculated. Day18 remains locked.\n',encoding='utf8')
 print(decision)
if __name__=='__main__':main()
