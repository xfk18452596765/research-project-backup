from __future__ import annotations
import hashlib, json
from pathlib import Path
STAGE=Path(__file__).resolve().parents[1]; REPO=STAGE.parents[1]
HISTORICAL=[REPO/'daily'/x for x in ('PreDay18_最小止损路线','PreDay18_Fixed-PRMAC机制诊断','PreDay18_ns3语义正确基线重建','PreDay18_语义正确基线止损复验')]
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def manifest(root):
 rows=[]; h=hashlib.sha256()
 for p in sorted((x for x in root.rglob('*') if x.is_file()),key=lambda x:x.relative_to(root).as_posix()):
  s=sha(p); r=p.relative_to(root).as_posix(); n=p.stat().st_size; rows.append({'path':r,'size':n,'sha256':s});h.update(f'{r}\0{n}\0{s}\n'.encode())
 return {'directory':root.relative_to(REPO).as_posix(),'file_count':len(rows),'sha256':h.hexdigest(),'files':rows}
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def load(p):return json.loads(p.read_text(encoding='utf8'))
