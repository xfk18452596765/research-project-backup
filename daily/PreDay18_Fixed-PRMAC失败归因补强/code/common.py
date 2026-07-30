from __future__ import annotations
import hashlib,json
from pathlib import Path
STAGE=Path(__file__).resolve().parents[1]; REPO=STAGE.parents[1]
HIST=[REPO/'daily'/x for x in ['PreDay18_最小止损路线','PreDay18_Fixed-PRMAC机制诊断','PreDay18_ns3语义正确基线重建','PreDay18_语义正确基线止损复验','PreDay18_Fixed-PRMAC机制重设计']]
def sha(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def write(p,v): p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def read(p): return json.loads(Path(p).read_text(encoding='utf8'))
def manifest(root):
 rows=[];h=hashlib.sha256()
 for p in sorted((x for x in root.rglob('*') if x.is_file()),key=lambda x:x.relative_to(root).as_posix()):
  s=sha(p);r=p.relative_to(root).as_posix();rows.append({'path':r,'sha256':s,'size':p.stat().st_size});h.update(f'{r}\0{s}\n'.encode())
 return {'directory':root.relative_to(REPO).as_posix(),'sha256':h.hexdigest(),'files':len(rows),'entries':rows}
