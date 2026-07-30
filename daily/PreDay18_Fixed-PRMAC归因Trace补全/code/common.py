from pathlib import Path
import hashlib,json
STAGE=Path(__file__).resolve().parents[1];REPO=STAGE.parents[1]
HIST=[REPO/'daily'/x for x in ['PreDay18_最小止损路线','PreDay18_Fixed-PRMAC机制诊断','PreDay18_ns3语义正确基线重建','PreDay18_语义正确基线止损复验','PreDay18_Fixed-PRMAC机制重设计','PreDay18_Fixed-PRMAC失败归因补强']]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def manifest(root):
 h=hashlib.sha256();n=0
 for p in sorted((x for x in root.rglob('*') if x.is_file()),key=lambda x:x.relative_to(root).as_posix()):h.update((p.relative_to(root).as_posix()+'\0'+sha(p)+'\n').encode());n+=1
 return {'directory':root.relative_to(REPO).as_posix(),'files':n,'sha256':h.hexdigest()}
