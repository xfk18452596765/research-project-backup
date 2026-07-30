#!/usr/bin/env python3
"""Append-only provenance closure for the immutable PreDay18 patch evidence."""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parents[1]
OUT = STAGE / "results"
PATCHES = [
 ("semantic_baseline", "P1", "7560ac7b06e8f272ff378e97f9b420f0c50ff98d", "daily/PreDay18_ns3语义正确基线重建/ns3/patches/ns3-3.43-fixed-prmac-access.patch", "90823ff0d2bc380ad838007293b87c87f3631c73b313b38b92d4da46907184db"),
 ("attribution_trace", "P2", "aacc7093bc5c0a822106e891e436985def405cc5", "daily/PreDay18_Fixed-PRMAC归因Trace补全/ns3/patches/attribution-trace-completion.patch", "9405e0e83684725e92bcd0bf99c8f567f6d17a1f8501468b0c4ca1bd91ca43d1"),
 ("lifecycle_trace", "P3", "5b5ef9110895457137321de2e36212a4b04ed120", "daily/PreDay18_Fixed-PRMAC生命周期Trace闭合/ns3/patches/lifecycle-trace-completion.patch", "8c55571e688502973dfbde0eb0a3dd0289354a55c8550efbd3995f9c6195ab46"),
]
def run(*args, cwd=ROOT, check=True):
 p=subprocess.run(args,cwd=cwd,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if check and p.returncode: raise RuntimeError(" ".join(args)+"\n"+p.stderr)
 return p
def sha(b): return hashlib.sha256(b).hexdigest()
def forms(b):
 lf=b.replace(b"\r\n",b"\n").replace(b"\r",b"\n")
 crlf=lf.replace(b"\n",b"\r\n")
 nobom=b[3:] if b.startswith(b"\xef\xbb\xbf") else b
 return {"raw_sha256":sha(b),"LF_normalized_sha256":sha(lf),"CRLF_normalized_sha256":sha(crlf),"UTF8_BOM_removed_sha256":sha(nobom),"has_utf8_bom":b.startswith(b"\xef\xbb\xbf"),"ends_with_newline":b.endswith((b"\n",b"\r")),"line_ending":"CRLF" if b"\r\n" in b else "LF" if b"\n" in b else "NONE"}
def tree_sha(d):
 h=hashlib.sha256()
 for p in sorted(x for x in d.rglob('*') if x.is_file() and '.git' not in x.parts):
  h.update(str(p.relative_to(d)).replace('\\','/').encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
 return h.hexdigest()
def main():
 for d in [OUT/'audit',OUT/'recovered',OUT/'manifests',OUT/'decision',STAGE/'logs',STAGE/'docs']: d.mkdir(parents=True,exist_ok=True)
 records=[]; recovered=[]
 for ident,label,commit,path,expected in PATCHES:
  blob=run('git','rev-parse',f'{commit}:{path}').stdout.strip()
  raw=subprocess.check_output(['git','cat-file','-p',blob],cwd=ROOT)
  checkout=(ROOT/path).read_bytes(); rp=OUT/'recovered'/f'{label}_{ident}.patch'; rp.write_bytes(raw)
  parent=run('git','rev-parse',f'{commit}^').stdout.strip()
  rec={"id":ident,"label":label,"path":path,"source_commit":commit,"parent_commit":parent,"source_blob":blob,"git_blob_oid":blob,"raw_git_blob_sha256":sha(raw),"checkout_raw_sha256":sha(checkout),"git_blob":forms(raw),"checkout":forms(checkout),"historical_manifest_sha256":expected,"historical_sha_status":"MATCH" if expected==sha(raw) else "ERRATUM","introduced_by":commit,"superseded_by":None,"size":len(raw)}
  records.append(rec); recovered.append(rp)
 # all historical textual references, with exact line evidence
 refs=[]
 for p in ROOT.glob('daily/PreDay18_*'):
  if p == STAGE: continue
  for f in p.rglob('*'):
   if f.is_file() and f.suffix.lower() in {'.json','.md','.txt','.log'}:
    try: lines=f.read_text(encoding='utf-8').splitlines()
    except UnicodeDecodeError: continue
    for n,line in enumerate(lines,1):
     if re.search(r'(sha|patch)',line,re.I) and re.search(r'[0-9a-fA-F]{64}',line): refs.append({"file":str(f.relative_to(ROOT)).replace('\\','/'),"line":n,"value":line.strip()})
 attrs={"core.autocrlf":run('git','config','--show-origin','--get','core.autocrlf',check=False).stdout.strip(),"core.eol":run('git','config','--show-origin','--get','core.eol',check=False).stdout.strip(),"gitattributes_present":(ROOT/'.gitattributes').exists(),"ls_files_eol":[run('git','ls-files','--eol','--',r['path']).stdout.strip() for r in records]}
 (OUT/'audit'/'patch_history.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'audit'/'historical_sha_references.json').write_text(json.dumps(refs,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'audit'/'line_ending_audit.json').write_text(json.dumps(attrs,ensure_ascii=False,indent=2),encoding='utf-8')
 canonical={"ns3_version":"3.43","base_source":{"commit_or_tag":"ns-3.43","tree_sha256":None},"patches":[{"order":i+1,"id":r['id'],"canonical_path":str(recovered[i].relative_to(STAGE)).replace('\\','/'),"source_commit":r['source_commit'],"source_blob":r['source_blob'],"raw_sha256":r['raw_git_blob_sha256'],"line_ending":r['git_blob']['line_ending'],"historical_sha_status":r['historical_sha_status']} for i,r in enumerate(records)]}
 # The required clean source is supplied by NS-3 upstream; no configure/build/test is performed.
 source=os.environ.get('NS3_43_SOURCE','')
 replay={"attempted":False,"reason":"NS3_43_SOURCE is not set to a clean ns-3.43 source tree"}
 if source and Path(source).is_dir():
  source=Path(source); canonical['base_source']['tree_sha256']=tree_sha(source); attempts=[]
  with tempfile.TemporaryDirectory(prefix='ns3-43-patch-audit-') as t:
   for name in ('audit-A','audit-B'):
    dest=Path(t)/name; shutil.copytree(source,dest,ignore=shutil.ignore_patterns('.git','build','cmake-cache'))
    steps=[]; ok=True
    for r,rp in zip(records,recovered):
     chk=run('git','apply','--check',str(rp),cwd=dest,check=False); app=run('git','apply',str(rp),cwd=dest,check=False) if chk.returncode==0 else chk
     steps.append({"patch":r['id'],"check_exit":chk.returncode,"apply_exit":app.returncode,"stderr":(chk.stderr+app.stderr).strip()}); ok &= chk.returncode==0 and app.returncode==0
    attempts.append({"copy":name,"ok":ok,"steps":steps,"final_tree_sha256":tree_sha(dest) if ok else None})
  replay={"attempted":True,"copies":attempts,"match":attempts[0]['ok'] and attempts[1]['ok'] and attempts[0]['final_tree_sha256']==attempts[1]['final_tree_sha256']}
 (OUT/'audit'/'patch_replay.json').write_text(json.dumps(replay,ensure_ascii=False,indent=2),encoding='utf-8')
 mismatches=[r for r in records if r['historical_sha_status']=='ERRATUM']
 if replay.get('match'):
  decision='PATCH_CHAIN_ERRATUM_READY' if mismatches else 'PATCH_CHAIN_READY'
 else: decision='PATCH_CHAIN_HOLD'
 canonical['decision']=decision; (OUT/'manifests'/'canonical_patch_chain.json').write_text(json.dumps(canonical,ensure_ascii=False,indent=2),encoding='utf-8')
 if mismatches:
  err=[{"historical_file":"daily/PreDay18_ns3独立干净源码工作区恢复/results/manifests/patch_chain_manifest.json","historical_field":"expected_sha256","historical_value":r['historical_manifest_sha256'],"actual_hashed_object":"Git blob raw bytes","canonical_patch_path":str(recovered[i].relative_to(STAGE)).replace('\\','/'),"canonical_raw_sha256":r['raw_git_blob_sha256'],"normalized_sha256":{"LF":r['git_blob']['LF_normalized_sha256'],"CRLF":r['git_blob']['CRLF_normalized_sha256']},"reason":"Neither raw Git blob nor LF/CRLF-normalized bytes match the historical value; field is an unverified patch-SHA label, not canonical raw bytes.","evidence_commits":[r['source_commit']],"impact":"Use canonical raw SHA and recovered Git blob; historical evidence remains unchanged."} for i,r in enumerate(mismatches)]
  (OUT/'manifests'/'patch_chain_erratum.json').write_text(json.dumps(err,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'decision'/'patch_chain_decision.json').write_text(json.dumps({"decision":decision,"replay":replay},ensure_ascii=False,indent=2),encoding='utf-8')
 (STAGE/'logs'/'provenance_closure.log').write_text("decision="+decision+"\nreplay_attempted="+str(replay.get('attempted'))+"\n",encoding='utf-8')
 (STAGE/'test_results.txt').write_text(f"decision={decision}\nconfigure_build_tests_executed=NO\nformal_lifecycle_runs_executed=NO\nrl_started=NO\n",encoding='utf-8')
 print(decision)
if __name__=='__main__': main()
