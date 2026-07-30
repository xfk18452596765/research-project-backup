#!/usr/bin/env python3
"""Read-only provenance closure for the three ns-3 patch artifacts.

This program never configures, builds, or tests ns-3.  It only obtains bytes
from this repository's Git object database and applies them to disposable
copies supplied with --ns3-source.
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE.parents[1]
PATCH_NAMES = [
    ("semantic_baseline", "ns3-3.43-fixed-prmac-access.patch"),
    ("attribution_trace", "attribution-trace-completion.patch"),
    ("lifecycle_trace", "lifecycle-trace-completion.patch"),
]

def run(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(args, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                       capture_output=True)
    if check and p.returncode:
        raise RuntimeError(f"{' '.join(args)}\n{p.stdout}\n{p.stderr}")
    return p

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def normalized(data: bytes, crlf: bool = False, remove_bom: bool = False) -> str:
    if remove_bom and data.startswith(b"\xef\xbb\xbf"): data = data[3:]
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if crlf: data = data.replace(b"\n", b"\r\n")
    return sha(data)
def eol(data: bytes) -> str:
    crlf, lf = data.count(b"\r\n"), data.count(b"\n")
    return "CRLF" if crlf and crlf == lf else "LF" if lf else "NONE" if not data else "MIXED"
def dump(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
def tree_sha(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(x for x in path.rglob("*") if x.is_file() and ".git" not in x.parts):
        h.update(f.relative_to(path).as_posix().encode()+b"\0"+hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()

def locate() -> list[dict]:
    found = []
    for ident, name in PATCH_NAMES:
        paths = [p for p in ROOT.joinpath("daily").rglob(name) if p.is_file()]
        if len(paths) != 1: raise RuntimeError(f"expected exactly one {name}, found {paths}")
        path = paths[0]; rel = path.relative_to(ROOT).as_posix()
        index = run("git", "ls-files", "-s", "--", rel).stdout.strip().split()
        blob = index[1]
        history = [line.split("\t") for line in run("git", "log", "--all", "--follow", "--format=%H%x09%P%x09%s", "--", rel).stdout.splitlines()]
        if not history: raise RuntimeError(f"no Git history for {rel}")
        raw = subprocess.run(["git", "cat-file", "-p", blob], cwd=ROOT, capture_output=True, check=True).stdout
        shown = subprocess.run(["git", "show", f"{history[0][0]}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout
        if raw != shown: raise RuntimeError(f"git show/cat-file disagreement: {rel}")
        found.append({"id": ident, "path": rel, "blob": blob, "raw": raw,
                      "checkout_matches_blob": raw == path.read_bytes(),
                      "history": [{"commit": x[0], "parents": x[1].split(), "subject": x[2]} for x in history]})
    return found

def references() -> list[dict]:
    records=[]
    candidates=[p for p in ROOT.joinpath("daily").rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".md", ".txt", ".log"}]
    for p in candidates:
        try: text=p.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError: continue
        for n,line in enumerate(text.splitlines(), 1):
            if "patch" not in line.lower(): continue
            for value in re.findall(r"(?i)\b[a-f0-9]{64}\b", line):
                records.append({"file":p.relative_to(ROOT).as_posix(),"line":n,"value":value.lower(),"line_text":line[:500],"object_definition":"unverified historical field"})
    return records

def replay(ns3: Path, patches: list[dict], audit: Path) -> dict:
    result={"source":str(ns3),"source_tree_sha256":tree_sha(ns3),"steps":[]}
    work=Path(tempfile.mkdtemp(prefix="ns3-43-patch-chain-", dir=audit))
    try:
        for label in ("audit-A", "audit-B"):
            dst=work/label; shutil.copytree(ns3, dst, ignore=shutil.ignore_patterns(".git"))
            steps=[]; ok=True
            for p in patches:
                saved=STAGE/"results"/"recovered"/(p["id"]+".patch")
                chk=run("git","apply","--check",str(saved),cwd=dst,check=False)
                step={"id":p["id"],"check_exit_code":chk.returncode,"check_stderr":chk.stderr.strip()}
                if chk.returncode == 0:
                    ap=run("git","apply",str(saved),cwd=dst,check=False)
                    step["apply_exit_code"]=ap.returncode
                    step["changed_files"]=run("git","diff","--name-only",cwd=dst,check=False).stdout.splitlines()
                    ok &= ap.returncode == 0
                else: ok=False
                steps.append(step)
                if not ok: break
            result[label]={"success":ok,"steps":steps,"final_tree_sha256":tree_sha(dst) if ok else None}
        result["match"] = result["audit-A"]["success"] and result["audit-B"]["success"] and result["audit-A"]["final_tree_sha256"] == result["audit-B"]["final_tree_sha256"]
    finally: shutil.rmtree(work, ignore_errors=True)
    return result

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--ns3-source", type=Path); args=ap.parse_args()
    audit=STAGE/"results"/"audit"; manifests=STAGE/"results"/"manifests"; audit.mkdir(parents=True,exist_ok=True)
    patches=locate(); refs=references()
    attrs=[]
    for p in patches:
        data=p.pop("raw")
        recovered=STAGE/"results"/"recovered"/(p["id"]+".patch"); recovered.parent.mkdir(parents=True,exist_ok=True); recovered.write_bytes(data)
        checkout=Path(ROOT/p["path"]).read_bytes()
        p.update({"git_blob_sha1":p["blob"],"raw_git_blob_sha256":sha(data),"checkout_raw_sha256":sha(checkout),"LF_normalized_sha256":normalized(data),"CRLF_normalized_sha256":normalized(data,True),"UTF8_BOM_removed_sha256":normalized(data,remove_bom=True),"line_ending":eol(data),"checkout_line_ending":eol(checkout),"bom":data.startswith(b"\xef\xbb\xbf"),"checkout_bom":checkout.startswith(b"\xef\xbb\xbf"),"trailing_newline":data.endswith((b"\n",b"\r"))})
        p["historical_references"]=[r for r in refs if r["value"] == p["raw_git_blob_sha256"]]
        attrs.append({"path":p["path"],"check_attr":run("git","check-attr","-a","--",p["path"]).stdout.strip(),"ls_files_eol":run("git","ls-files","--eol","--",p["path"]).stdout.strip()})
    config={k:run("git","config","--show-origin","--get",k,check=False).stdout.strip() for k in ("core.autocrlf","core.eol")}
    dump(audit/"patch_history.json",patches); dump(audit/"historical_sha_references.json",refs); dump(audit/"line_ending_audit.json",{"git_config":config,"gitattributes_exists":(ROOT/".gitattributes").exists(),"patches":attrs})
    chain={"ns3_version":"3.43","base_source":{"commit_or_tag":"ns-3.43","tree_sha256":tree_sha(args.ns3_source) if args.ns3_source else None},"patches":[{"order":i+1,"id":p["id"],"canonical_path":str((STAGE/"results"/"recovered"/(p["id"]+".patch")).relative_to(ROOT)).replace("\\","/"),"source_commit":p["history"][0]["commit"],"source_blob":p["blob"],"raw_sha256":p["raw_git_blob_sha256"],"line_ending":p["line_ending"],"historical_sha_status":"ERRATUM"} for i,p in enumerate(patches)]}
    dump(manifests/"canonical_patch_chain.json",chain)
    errata=[]
    known_errors=[("attribution_trace", "9405e0e83684725e92bcd0bf99c8f567f6d17a1f8501468b0c4ca1bd91ca43d1", "attribution patch field hashes the attribution-hold manifest, not the patch"),
                  ("lifecycle_trace", "b8f27455f40b4a4c946bb7ee2a32d2432d1b5cbf2ed48721d3665f375ab89ccd", "lifecycle patch field hashes the CRLF checkout bytes, not the canonical Git blob")]
    for ident,value,reason in known_errors:
        p=next(x for x in patches if x["id"] == ident)
        hits=[r for r in refs if r["value"] == value]
        for r in hits:
            errata.append({"historical_file":r["file"],"historical_field":"patch SHA (context recorded)","historical_value":value,"actual_hashed_object":reason,"canonical_patch_path":p["path"],"canonical_raw_sha256":p["raw_git_blob_sha256"],"normalized_sha256":p["LF_normalized_sha256"],"reason":"HASH_OBJECT_LABEL_ERROR","evidence_commits":[x["commit"] for x in p["history"]],"impact":"use canonical patch chain, not this historical value"})
    dump(manifests/"patch_chain_erratum.json",{"append_only":True,"errata":errata})
    replay_result={"not_run_reason":"ns3 source not supplied"} if not args.ns3_source else replay(args.ns3_source,patches,audit)
    dump(audit/"patch_dry_run.json",replay_result)
    decision="PATCH_CHAIN_ERRATUM_READY" if replay_result.get("match") and errata else "PATCH_CHAIN_READY" if replay_result.get("match") else "PATCH_CHAIN_HOLD"
    dump(STAGE/"results"/"decision"/"patch_chain_decision.json",{"decision":decision,"erratum_count":len(errata),"dry_run":replay_result})
    (STAGE/"test_results.txt").write_text(f"patch provenance tests: PASS\npatch dry-run: {'PASS' if replay_result.get('match') else 'NOT PASS'}\ndecision: {decision}\nconfigure/build/tests executed: NO\n",encoding="utf-8",newline="\n")
    print(decision)
    return 0 if decision != "PATCH_CHAIN_HOLD" else 2
if __name__ == "__main__": raise SystemExit(main())
