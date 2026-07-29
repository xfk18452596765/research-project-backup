from __future__ import annotations
import csv,json
from pathlib import Path

def write_json(path: str|Path, value: object) -> None:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")

def read_json(path: str|Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def write_csv(path: str|Path, rows: list[dict]) -> None:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with p.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
