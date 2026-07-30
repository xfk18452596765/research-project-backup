import json
from pathlib import Path

stage = Path(__file__).resolve().parents[1]
history = json.loads((stage/'results/audit/patch_history.json').read_text(encoding='utf-8'))
replay = json.loads((stage/'results/audit/patch_replay.json').read_text(encoding='utf-8'))
assert len(history) == 3
assert history[0]['historical_sha_status'] == 'MATCH'
assert all(x['git_blob']['line_ending'] == 'LF' for x in history)
assert all(x['checkout']['line_ending'] == 'CRLF' for x in history)
assert replay['attempted'] is True and replay['match'] is False
assert all(x['ok'] is False for x in replay['copies'])
(stage/'test_results.txt').open('a', encoding='utf-8').write('provenance_artifact_checks=PASS\n')
print('provenance artifact checks: PASS')
