from __future__ import annotations

import subprocess
from pathlib import Path

from common import REPO, STAGE

BASELINE_REL = "daily/PreDay18_ns3语义正确基线重建/ns3/overlay/scratch/preday18-semantic-baseline.cc"


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one source match, found {text.count(old)}: {old[:80]!r}")
    return text.replace(old, new)


def generate() -> Path:
    source = subprocess.check_output(["git", "show", f"HEAD:{BASELINE_REL}"], cwd=REPO).decode("utf-8")
    source = replace_once(
        source,
        '    Ptr<UniformRandomVariable> retryRng;\n',
        '    Ptr<UniformRandomVariable> retryRng;\n'
        '    Ptr<UniformRandomVariable> faultRng;\n'
        '    double controlLoss{0.0};\n',
    )
    source = replace_once(
        source,
        '        Trace(node, h, FrameName(h.Type()) + "_RX", "", g.localFifos[node].size(),\n'
        '              packet->GetSize() + h.GetSerializedSize());\n'
        '        if (h.Type() == PROBE) { g.probeRx[node]++; continue; }\n',
        '        Trace(node, h, FrameName(h.Type()) + "_RX", "", g.localFifos[node].size(),\n'
        '              packet->GetSize() + h.GetSerializedSize());\n'
        '        if (h.Type() == PROBE) { g.probeRx[node]++; continue; }\n'
        '        if (g.controlLoss > 0.0 && h.Type() != DATA &&\n'
        '            g.faultRng->GetValue(0.0, 1.0) < g.controlLoss)\n'
        '        {\n'
        '            Trace(node, h, "CONTROL_FAULT_INJECTED",\n'
        '                  "probability=" + std::to_string(g.controlLoss));\n'
        '            continue;\n'
        '        }\n',
    )
    source = replace_once(
        source,
        '                 "chain|multiflow-m1|multiflow-m2|hidden|calibration|reservation-conflict",\n',
        '                 "chain|multiflow-m1|multiflow-m2|multiflow-m3|spatial|hidden|calibration|reservation-conflict",\n',
    )
    source = replace_once(
        source,
        '    cmd.AddValue("output", "JSON result path", g.outputPath);\n',
        '    cmd.AddValue("output", "JSON result path", g.outputPath);\n'
        '    cmd.AddValue("controlLoss", "logical Fixed control-frame loss probability", g.controlLoss);\n',
    )
    source = replace_once(
        source,
        '    NS_ABORT_MSG_IF(g.traffic != "periodic" && g.traffic != "poisson", "invalid traffic");\n'
        '    NS_ABORT_MSG_IF(g.load != "low" && g.load != "high", "invalid load");\n',
        '    NS_ABORT_MSG_IF(g.traffic != "periodic" && g.traffic != "poisson" &&\n'
        '                    g.traffic != "burst", "invalid traffic");\n'
        '    NS_ABORT_MSG_IF(g.load != "low" && g.load != "medium" && g.load != "high",\n'
        '                    "invalid load");\n'
        '    NS_ABORT_MSG_IF(g.controlLoss < 0.0 || g.controlLoss > 1.0, "invalid control loss");\n',
    )
    source = replace_once(
        source,
        '    if (g.scenario == "hidden")\n'
        '    {\n'
        '        nodeCount = 3;\n'
        '        g.hops = 1;\n'
        '        g.spacing = 30.0;\n'
        '    }\n',
        '    if (g.scenario == "hidden")\n'
        '    {\n'
        '        nodeCount = 3;\n'
        '        g.hops = 1;\n'
        '        g.spacing = 30.0;\n'
        '    }\n'
        '    else if (g.scenario == "spatial")\n'
        '    {\n'
        '        nodeCount = 7;\n'
        '        g.hops = 6;\n'
        '    }\n',
    )
    source = replace_once(
        source,
        '    for (uint32_t i = 0; i < nodeCount; ++i) { positions->Add(Vector(i * g.spacing, 0.0, 0.0)); }\n',
        '    for (uint32_t i = 0; i < nodeCount; ++i)\n'
        '    {\n'
        '        if (g.scenario == "spatial" && i >= 4)\n'
        '        {\n'
        '            positions->Add(Vector((i - 4) * g.spacing, 100.0, 0.0));\n'
        '        }\n'
        '        else { positions->Add(Vector(i * g.spacing, 0.0, 0.0)); }\n'
        '    }\n',
    )
    source = replace_once(
        source,
        '    if (g.scenario == "multiflow-m1") { g.flows = {{0, g.hops, 1}, {1, g.hops, 1}}; }\n'
        '    else if (g.scenario == "multiflow-m2") { g.flows = {{0, g.hops, 1}, {g.hops, 0, -1}}; }\n'
        '    else if (g.scenario == "hidden") { g.flows = {{0, 1, 1}, {2, 1, -1}}; }\n'
        '    else { g.flows = {{0, g.hops, 1}}; }\n',
        '    if (g.scenario == "multiflow-m1") { g.flows = {{0, g.hops, 1}, {1, g.hops, 1}}; }\n'
        '    else if (g.scenario == "multiflow-m2") { g.flows = {{0, g.hops, 1}, {g.hops, 0, -1}}; }\n'
        '    else if (g.scenario == "multiflow-m3") { g.flows = {{0, 4, 1}, {2, 6, 1}}; }\n'
        '    else if (g.scenario == "spatial") { g.flows = {{0, 2, 1}, {4, 6, 1}}; }\n'
        '    else if (g.scenario == "hidden") { g.flows = {{0, 1, 1}, {2, 1, -1}}; }\n'
        '    else { g.flows = {{0, g.hops, 1}}; }\n',
    )
    source = replace_once(
        source,
        '    g.retryRng = CreateObject<UniformRandomVariable>();\n'
        '    g.retryRng->SetStream(g.seed + 1000);\n'
        '    double time = 1.0;\n'
        '    const double interval = g.load == "high" ? 0.002 : 0.12;\n',
        '    g.retryRng = CreateObject<UniformRandomVariable>();\n'
        '    g.retryRng->SetStream(g.seed + 1000);\n'
        '    g.faultRng = CreateObject<UniformRandomVariable>();\n'
        '    g.faultRng->SetStream(g.seed + 2000);\n'
        '    Ptr<ExponentialRandomVariable> arrival = CreateObject<ExponentialRandomVariable>();\n'
        '    arrival->SetAttribute("Mean", DoubleValue(g.load == "low" ? 0.050 :\n'
        '                                               (g.load == "medium" ? 0.020 : 0.008)));\n'
        '    arrival->SetStream(g.seed);\n'
        '    double time = 1.0;\n'
        '    const double interval = g.load == "low" ? 0.050 : (g.load == "medium" ? 0.020 : 0.008);\n',
    )
    source = replace_once(
        source,
        '            time += g.traffic == "poisson" ? random->GetValue(0.5, 1.5) * interval : interval;\n',
        '            if (g.traffic == "poisson") { time += arrival->GetValue(); }\n'
        '            else if (g.traffic == "burst")\n'
        '            {\n'
        '                time += (packet % 5 == 4) ? (5 * interval - 0.004) : 0.001;\n'
        '            }\n'
        '            else { time += interval; }\n',
    )
    destination = STAGE / "ns3" / "source" / "preday18-stop-loss-retest.cc"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source, encoding="utf-8", newline="\n")
    return destination


if __name__ == "__main__":
    print(generate())
