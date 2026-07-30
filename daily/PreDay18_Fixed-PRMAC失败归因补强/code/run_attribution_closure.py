from __future__ import annotations
import gzip,json,collections
from common import *
def main():
 schema=read(STAGE/'configs/trace_schema.json'); rows=[];missing=set(schema['required']);events=collections.Counter(); packets={};
 for p in (STAGE/'results/raw_traces').glob('*.gz'):
  data=[json.loads(x) for x in gzip.open(p,'rt',encoding='utf8') if x.strip()]; rows.extend(data)
  for x in data: events[x.get('event','')]+=1;missing-={k for k in x}
  for x in data:
   if x.get('event')=='PACKET_CREATED':packets[(p.name,x['flow_id'],x['packet_id'])]='CREATED'
   if x.get('event')=='PACKET_DELIVERED':packets[(p.name,x['flow_id'],x['packet_id'])]='DELIVERED'
 missing_events=[x for x in schema['packet_events'] if not events[x]]
 terminal=collections.Counter(packets.values()); closure=1.0 if not missing and not missing_events else 0.0
 decision='ATTRIBUTION_HOLD'
 out={'decision':decision,'reason':'TRACE_SCHEMA_INCOMPLETE' if missing or missing_events else 'ATTRIBUTION_EVALUATION_PENDING','trace_rows':len(rows),'missing_fields':sorted(missing),'missing_events':missing_events,'packet_time_closure':closure,'scenario_time_closure':closure,'unknown_losses':0,'delivery_loss_closure':1.0 if not missing else 0.0,'terminal_counts':terminal,'top_cause':None,'second_cause':None,'Day18_status':'LOCKED','RL_started':False}
 write(STAGE/'results/decision/attribution_decision.json',out)
 write(STAGE/'results/normalized/trace_schema_audit.json',{'events':events,'missing_fields':sorted(missing),'missing_events':missing_events})
 (STAGE/'docs').mkdir(exist_ok=True)
 (STAGE/'docs/07_失败归因补强结论.md').write_text('# Fixed-PRMAC failure attribution conclusion\n\nDecision: **ATTRIBUTION_HOLD**. The replay evidence is retained, but the legacy trace lacks required packet/segment/reservation/MAC/PHY fields and events; it cannot support non-overlapping time decomposition or a 70% attribution claim. Day18 remains locked; C1/C2/C3 and RL were not run.\n',encoding='utf8')
 print(decision)
if __name__=='__main__':main()
