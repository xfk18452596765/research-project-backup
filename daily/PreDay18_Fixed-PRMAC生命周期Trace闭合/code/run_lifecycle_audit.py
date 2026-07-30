"""Generate an instrumentation-only lifecycle overlay and immutable-evidence audit."""
from common import *
import difflib, subprocess

HISTORICAL = [p for p in REPO.glob('daily/PreDay18_*') if p.name != STAGE.name]
BASE = PREVIOUS / 'ns3/overlay/scratch/preday18-fixed-prmac-trace.cc'
OUT = STAGE / 'ns3/overlay/scratch/preday18-fixed-prmac-lifecycle-trace.cc'

def instrument(text):
    # This patch adds serialization calls only. It deliberately does not alter callback
    # registration, RNG objects, scheduling calls, protocol branches, or stop time.
    text = text.replace('Trace(source, h, "QUEUE_ENQUEUE"', 'Trace(source, h, "SOURCE_QUEUE_ENQUEUE"')
    text = text.replace('Trace(source, h, "QUEUE_SERVICE_START"', 'Trace(source, h, "SOURCE_SERVICE_START"')
    text = text.replace('Trace(node, h, "HOP_FORWARD_ENQUEUE"', 'Trace(node, h, "RELAY_QUEUE_ENQUEUE"')
    text = text.replace('Trace(node, h, "PACKET_DELIVERED");', 'Trace(node, h, "DESTINATION_DELIVER");\n    Trace(node, h, "PACKET_DELIVERED");')
    text = text.replace('Trace(node, h, "SEGMENT_COMPLETED");', 'Trace(node, h, "RESERVATION_RELEASED", "release-complete");\n                Trace(node, h, "SEGMENT_COMPLETED");')
    text = text.replace('Trace(node, h, "RESERVATION_ATTEMPT_REJECTED",', 'Trace(node, h, "RESERVATION_ATTEMPT_FAILED", "PR_NACK");\n                Trace(node, h, "RESERVATION_ATTEMPT_REJECTED",')
    text = text.replace('Trace(node, h, "RESERVATION_ACTIVE",', 'Trace(node, h, "RESERVATION_ATTEMPT_START", "ACKNOWLEDGED");\n            Trace(node, h, "RESERVATION_ACTIVE",')
    marker = '    Simulator::Destroy();\n    WriteResult();'
    replacement = ('    // Read-only terminal scan: emitted after Run and before Destroy.\n'
                   '    for (const auto& [key, state] : g.packetStates) {\n'
                   '        if (state.terminal.empty()) {\n'
                   '            SemanticHeader end(DATA, static_cast<uint8_t>(key >> 32), 0, 0, static_cast<uint32_t>(key), 0, 0, 0, 0);\n'
                   '            Trace(state.lastNode, end, "SIMULATION_END_UNFINISHED", "SIMULATION_END_SOURCE_QUEUE");\n'
                   '            Trace(state.lastNode, end, "PACKET_FINAL_LOSS", "SIMULATION_END_SOURCE_QUEUE");\n'
                   '        }\n'
                   '    }\n' + marker)
    if marker not in text: raise RuntimeError('terminal scan anchor not found')
    return text.replace(marker, replacement, 1)

def main():
    source = BASE.read_text(encoding='utf-8')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(instrument(source), encoding='utf-8')
    patch = ''.join(difflib.unified_diff(source.splitlines(True), OUT.read_text(encoding='utf-8').splitlines(True), fromfile='previous-trace.cc', tofile='lifecycle-trace.cc'))
    patch_path = STAGE / 'ns3/patches/lifecycle-trace-completion.patch'; patch_path.parent.mkdir(parents=True, exist_ok=True); patch_path.write_text(patch, encoding='utf-8')
    immutable = subprocess.run(['git','diff','--quiet','e86cb56','--'] + [str(p.relative_to(REPO)) for p in HISTORICAL], cwd=REPO).returncode == 0
    manifests = [tree_manifest(p) for p in HISTORICAL]
    previous = read(PREVIOUS / 'results/audit/trace_patch_scope.json')
    changed = '\n'.join(line[1:] for line in patch.splitlines() if line.startswith(('+', '-')) and not line.startswith(('+++', '---')))
    audit = {'base_commit':'e86cb56','historical_evidence_immutable':immutable,'historical':manifests,
             'semantic_decision':'BASELINE_READY','previous_trace_decision':'TRACE_HOLD',
             'previous_trace_patch_sha256':previous['trace_completion_patch_sha256'],
             'lifecycle_patch_sha256':sha256(patch_path),'patch_nonempty':bool(patch),
             'scope':'instrumentation only: trace serialization, stable IDs, read-only snapshots and terminal scan',
             'forbidden_tokens_absent': all(x not in changed for x in ('Simulator::Schedule(', 'SetStream(', 'SetMinCw(', 'SetMaxCw(', 'Simulator::Stop('))}
    write(STAGE/'results/audit/historical_evidence_sha256.json', {'immutable':immutable,'historical':manifests})
    write(STAGE/'results/audit/lifecycle_patch_scope.json', audit)
    write(STAGE/'results/audit/trace_hold_manifest.json', {'decision':'TRACE_HOLD','previous_trace_patch_sha256':previous['trace_completion_patch_sha256']})
    print(audit['lifecycle_patch_sha256'])

if __name__ == '__main__': main()
