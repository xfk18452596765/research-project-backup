"""Create an instrumentation-only overlay; the original semantic source remains untouched."""
from common import *
import re
SRC=REPO/'daily/PreDay18_语义正确基线止损复验/ns3/source/preday18-stop-loss-retest.cc'
OUT=STAGE/'ns3/overlay/scratch/preday18-fixed-prmac-trace.cc'
def main():
 s=SRC.read_text(encoding='utf8')
 s=s.replace('std::ofstream trace;','std::ofstream trace;\n    bool traceEnabled{false};')
 s=s.replace('void\nTrace(uint32_t node,','uint64_t AirNs(uint32_t bytes) { return uint64_t(bytes) * 8 * 1000; }\n\nvoid\nTrace(uint32_t node,')
 old='''{\n    g.trace << "{\\\"time_us\\\":" << Simulator::Now().GetMicroSeconds() << ",\\\"node_id\\\":" << node'''
 new='''{\n    if (!g.traceEnabled) { return; }\n    const uint64_t timeNs = Simulator::Now().GetNanoSeconds();\n    const uint32_t bytes = actualSize;\n    const uint32_t cw = (reason.find("CW=") == std::string::npos) ? CW_MIN : static_cast<uint32_t>(std::stoul(reason.substr(reason.find("CW=") + 3)));\n    g.trace << "{\\\"schema_version\\\":\\\"2.0\\\",\\\"time_ns\\\":" << timeNs << ",\\\"time_us\\\":" << Simulator::Now().GetMicroSeconds() << ",\\\"node_id\\\":" << node'''
 if old not in s: raise RuntimeError('Trace body anchor not found')
 s=s.replace(old,new,1)
 anchor='''<< h.Segment() << "\\\",\\\"logical_size\\\":" << actualSize << "}\\n";\n}'''
 replacement='''<< h.Segment() << "\\\",\\\"logical_size\\\":" << actualSize
            << ",\\\"sender\\\":" << node << ",\\\"receiver\\\":" << node
            << ",\\\"cw\\\":" << cw << ",\\\"backoff_slots\\\":0,\\\"channel_state\\\":\\\"UNKNOWN\\\",\\\"reservation_state\\\":\\\"SNAPSHOT\\\",\\\"frame_bytes\\\":" << bytes << ",\\\"logical_control_bytes\\\":" << ((h.Type() == DATA) ? 0 : bytes) << ",\\\"phy_airtime_ns\\\":" << AirNs(bytes) << ",\\\"random_stream_id\\\":0}\\n";
}'''
 if anchor not in s: raise RuntimeError('Trace end anchor not found')
 s=s.replace(anchor,replacement,1)
 s=s.replace('cmd.AddValue("controlLoss", "logical Fixed control-frame loss probability", g.controlLoss);','cmd.AddValue("controlLoss", "logical Fixed control-frame loss probability", g.controlLoss);\n    cmd.AddValue("traceEnabled", "enable instrumentation serialization", g.traceEnabled);')
 s=s.replace('g.trace.open(g.tracePath);\n    NS_ABORT_MSG_IF(!g.trace, "cannot open trace output");','if (g.traceEnabled) { g.trace.open(g.tracePath); NS_ABORT_MSG_IF(!g.trace, "cannot open trace output"); }')
 s=s.replace('g.trace.close();\n    WriteResult();','WriteResult();\n    if (g.traceEnabled) { g.trace.close(); }')
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(s,encoding='utf8')
 print(sha(OUT))
if __name__=='__main__':main()
