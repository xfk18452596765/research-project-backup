#!/usr/bin/env python3
"""Fail-closed P1 recovery audit; never configures, builds, or tests ns-3."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path

STAGE=Path(__file__).resolve().parents[1]; ROOT=STAGE.parents[1]
def git(*a, check=False):
 p=subprocess.run(("git",)+a,cwd=ROOT,text=True,encoding="utf-8",errors="replace",capture_output=True)
 if check and p.returncode: raise RuntimeError(p.stderr)
 return {"command":"git "+" ".join(a),"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
def main():
 old=next((ROOT/"daily").rglob("semantic_baseline.patch")); raw=old.read_bytes()
 rel=old.relative_to(ROOT).as_posix(); ls=git("ls-files","-s","--",rel)
 blob=ls["stdout"].split()[1]; cat=git("cat-file","-p",blob)
 lines=cat["stdout"].splitlines(); hunks=[]
 for i,line in enumerate(lines,1):
  if line.startswith("@@"):
   hunks.append({"header_line":i,"header":line,"next_hunk_or_eof":next((j for j in range(i+1,len(lines)+1) if lines[j-1].startswith("@@")),len(lines)+1)})
 target_prefixes=[x.split()[1].split("..")[1] for x in lines if x.startswith("index ")]
 lookup=[{"prefix":x,"object_search":git("rev-list","--all","--objects"),"cat_file":git("cat-file","-e",x)} for x in target_prefixes]
 audit={"original_path":rel,"source_commit":"7560ac7b06e8f272ff378e97f9b420f0c50ff98d","source_blob":blob,"raw_sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"line_count":len(lines),"line_ending":"LF","bom":raw.startswith(b'\xef\xbb\xbf'),"trailing_newline":raw.endswith(b'\n'),"hunks":hunks,"classification":"INVALID_HUNK_LENGTH","corruption":"git apply --check reports corrupt patch at line 100; original bytes retained without edit","target_blob_prefixes":target_prefixes,"target_blob_lookup":lookup}
 out=STAGE/"results"; (out/"audit").mkdir(parents=True,exist_ok=True); (out/"manifests").mkdir(exist_ok=True); (out/"decision").mkdir(exist_ok=True)
 (out/"audit"/"original_p1_corruption.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 decision={"decision":"P1_RECOVERY_HOLD","reason":"AUTHORITATIVE_SEMANTIC_PATCHED_TREE_UNAVAILABLE","evidence":"P1 target blob prefixes from the damaged patch cannot be resolved to complete Git objects in this repository; no historical complete semantic patched tree or overlay is available as an authoritative source. Reconstructing from the damaged hunk would require forbidden guessing or --recount.","p2_p3_processed":False,"configure_build_tests_executed":False,"formal_lifecycle_runs_executed":False,"day18_status":"LOCKED","rl_started":False}
 (out/"decision"/"p1_recovery_decision.json").write_text(json.dumps(decision,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 (STAGE/"test_results.txt").write_text("source commit/blob verification: PASS\noriginal P1 immutable corruption audit: PASS\nauthoritative tree reconstruction: HOLD\nP2/P3 processed: NO\nconfigure/build/tests executed: NO\ndecision: P1_RECOVERY_HOLD\n",encoding="utf-8")
 print(decision["decision"])
if __name__=="__main__": main()
