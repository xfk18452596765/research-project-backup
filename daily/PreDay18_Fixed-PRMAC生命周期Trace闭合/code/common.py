"""Shared, read-only-safe helpers for the lifecycle trace closure stage."""
from pathlib import Path
import hashlib, json

STAGE = Path(__file__).resolve().parents[1]
REPO = STAGE.parents[1]
PREVIOUS = next(REPO.glob('daily/PreDay18_Fixed-PRMAC*Trace*'))

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def tree_manifest(root):
    h = hashlib.sha256(); count = 0
    for path in sorted((p for p in Path(root).rglob('*') if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        h.update((path.relative_to(root).as_posix() + '\0' + sha256(path) + '\n').encode())
        count += 1
    return {'directory': Path(root).relative_to(REPO).as_posix(), 'files': count, 'sha256': h.hexdigest()}
