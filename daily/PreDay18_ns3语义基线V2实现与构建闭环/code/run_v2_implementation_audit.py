#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,subprocess
S=Path(__file__).resolve().parents[1]; M=S/'ns3'/'manifests'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 M.mkdir(parents=True,exist_ok=True)
 a=Path(r'C:\workspace\ns-3.43-semantic-v2-A'); b=Path(r'C:\workspace\ns-3.43-semantic-v2-B')
 commit=subprocess.check_output(['git','-C',str(a),'rev-parse','HEAD'],text=True).strip()
 overlay=S/'ns3'/'overlay'/'scratch'/'preday18-semantic-baseline-v2.cc'
 data={'origin':'https://gitlab.com/nsnam/ns-3-dev.git','tag':'ns-3.43','commit':commit,'clean_tree_git_commit':commit}
 for name,root in [('clean_source_A.json',a),('clean_source_B.json',b)]: (M/name).write_text(json.dumps(data,indent=2)+'\\n')
 f={'relative_path':'scratch/preday18-semantic-baseline-v2.cc','change_type':'add','raw_sha256':sha(overlay),'mode':'0644','purpose':'real ns-3 Wi-Fi DCF chain smoke executable'}
 for name in ['overlay_manifest.json','changed_file_set.json']: (M/name).write_text(json.dumps([f],indent=2)+'\\n')
 print(json.dumps({'clean_A':commit,'clean_B':commit,'overlay_sha256':sha(overlay),'patch_sha256':sha(S/'ns3'/'patches'/'semantic-baseline-v2.patch')},indent=2))
if __name__=='__main__': main()
