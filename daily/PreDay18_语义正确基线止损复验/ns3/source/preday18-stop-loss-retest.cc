#include "ns3/command-line.h"
#include "ns3/config.h"
#include "ns3/double.h"
#include "ns3/mobility-helper.h"
#include "ns3/network-module.h"
#include "ns3/packet-socket-address.h"
#include "ns3/packet-socket-helper.h"
#include "ns3/rng-seed-manager.h"
#include "ns3/string.h"
#include "ns3/txop.h"
#include "ns3/uinteger.h"
#include "ns3/wifi-module.h"
#include "ns3/yans-wifi-channel.h"
#include "ns3/yans-wifi-helper.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <deque>
#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

namespace
{

constexpr uint32_t K = 2;
constexpr uint32_t CW_MIN = 15;
constexpr uint32_t CW_MAX = 1023;
constexpr uint32_t RETRY_LIMIT = 7;
constexpr uint32_t QUEUE_LIMIT = 200;
constexpr uint32_t DATA_BYTES = 1024;
constexpr uint32_t PR_REQ_BYTES = 36;
constexpr uint32_t PR_ACK_BYTES = 24;
constexpr uint32_t PR_NACK_BYTES = 24;
constexpr uint32_t H_ACK_BYTES = 14;
constexpr uint32_t RELEASE_BYTES = 20;
constexpr uint16_t PROTOCOL = 0x88b5;

enum FrameType : uint8_t
{
    DATA = 1,
    PR_REQ = 2,
    PR_ACK = 3,
    PR_NACK = 4,
    H_ACK = 5,
    RELEASE = 6,
    PROBE = 7,
    ORDINARY_SMOKE = 8
};

std::string
FrameName(uint8_t value)
{
    static const std::map<uint8_t, std::string> names = {{DATA, "DATA"},
                                                         {PR_REQ, "PR_REQ"},
                                                         {PR_ACK, "PR_ACK"},
                                                         {PR_NACK, "PR_NACK"},
                                                         {H_ACK, "H_ACK"},
                                                         {RELEASE, "RELEASE"},
                                                         {PROBE, "PROBE"},
                                                         {ORDINARY_SMOKE, "ORDINARY_SMOKE"}};
    auto it = names.find(value);
    return it == names.end() ? "UNKNOWN" : it->second;
}

class SemanticHeader : public Header
{
  public:
    SemanticHeader() = default;
    SemanticHeader(uint8_t type,
                   uint8_t flow,
                   uint8_t attempt,
                   uint8_t flags,
                   uint32_t packet,
                   uint16_t segment,
                   uint16_t hop,
                   uint16_t start,
                   uint16_t end)
        : m_type(type),
          m_flow(flow),
          m_attempt(attempt),
          m_flags(flags),
          m_packet(packet),
          m_segment(segment),
          m_hop(hop),
          m_start(start),
          m_end(end)
    {
    }

    static TypeId GetTypeId()
    {
        static TypeId tid =
            TypeId("ns3::Preday18SemanticHeader")
                .SetParent<Header>()
                .SetGroupName("Network")
                .AddConstructor<SemanticHeader>();
        return tid;
    }
    TypeId GetInstanceTypeId() const override
    {
        return GetTypeId();
    }
    uint32_t GetSerializedSize() const override
    {
        return 14;
    }
    void Serialize(Buffer::Iterator i) const override
    {
        i.WriteU8(m_type);
        i.WriteU8(m_flow);
        i.WriteU8(m_attempt);
        i.WriteU8(m_flags);
        i.WriteHtonU32(m_packet);
        i.WriteHtonU16(m_segment);
        i.WriteHtonU16(m_hop);
        i.WriteU8(static_cast<uint8_t>(m_start));
        i.WriteU8(static_cast<uint8_t>(m_end));
    }
    uint32_t Deserialize(Buffer::Iterator i) override
    {
        m_type = i.ReadU8();
        m_flow = i.ReadU8();
        m_attempt = i.ReadU8();
        m_flags = i.ReadU8();
        m_packet = i.ReadNtohU32();
        m_segment = i.ReadNtohU16();
        m_hop = i.ReadNtohU16();
        m_start = i.ReadU8();
        m_end = i.ReadU8();
        return GetSerializedSize();
    }
    void Print(std::ostream& os) const override
    {
        os << FrameName(m_type) << " flow=" << +m_flow << " packet=" << m_packet
           << " segment=" << m_segment << " hop=" << m_hop;
    }

    uint8_t Type() const { return m_type; }
    uint8_t Flow() const { return m_flow; }
    uint8_t Attempt() const { return m_attempt; }
    uint8_t Flags() const { return m_flags; }
    uint32_t PacketId() const { return m_packet; }
    uint16_t Segment() const { return m_segment; }
    uint16_t Hop() const { return m_hop; }
    uint16_t Start() const { return m_start; }
    uint16_t End() const { return m_end; }

  private:
    uint8_t m_type{0};
    uint8_t m_flow{0};
    uint8_t m_attempt{0};
    uint8_t m_flags{0};
    uint32_t m_packet{0};
    uint16_t m_segment{0};
    uint16_t m_hop{0};
    uint16_t m_start{0};
    uint16_t m_end{0};
};

class SemanticTag : public Tag
{
  public:
    SemanticTag() = default;
    explicit SemanticTag(const SemanticHeader& h)
        : m_type(h.Type()),
          m_flow(h.Flow()),
          m_packet(h.PacketId()),
          m_segment(h.Segment()),
          m_hop(h.Hop())
    {
    }
    static TypeId GetTypeId()
    {
        static TypeId tid =
            TypeId("ns3::Preday18SemanticTag").SetParent<Tag>().AddConstructor<SemanticTag>();
        return tid;
    }
    TypeId GetInstanceTypeId() const override { return GetTypeId(); }
    uint32_t GetSerializedSize() const override { return 11; }
    void Serialize(TagBuffer b) const override
    {
        b.WriteU8(m_type);
        b.WriteU8(m_flow);
        b.WriteU32(m_packet);
        b.WriteU16(m_segment);
        b.WriteU16(m_hop);
    }
    void Deserialize(TagBuffer b) override
    {
        m_type = b.ReadU8();
        m_flow = b.ReadU8();
        m_packet = b.ReadU32();
        m_segment = b.ReadU16();
        m_hop = b.ReadU16();
    }
    void Print(std::ostream& os) const override
    {
        os << FrameName(m_type) << ":" << +m_flow << ":" << m_packet << ":" << m_hop;
    }
    uint8_t Type() const { return m_type; }
    uint8_t Flow() const { return m_flow; }
    uint32_t PacketId() const { return m_packet; }
    uint16_t Segment() const { return m_segment; }
    uint16_t Hop() const { return m_hop; }

  private:
    uint8_t m_type{0};
    uint8_t m_flow{0};
    uint32_t m_packet{0};
    uint16_t m_segment{0};
    uint16_t m_hop{0};
};

struct Flow
{
    uint32_t source{0};
    uint32_t destination{0};
    int direction{1};
};

struct PacketState
{
    std::string terminal;
    uint32_t lastNode{0};
    uint32_t segmentsCompleted{0};
};

struct State
{
    std::string protocol{"dcf"};
    std::string scenario{"chain"};
    std::string traffic{"periodic"};
    std::string load{"low"};
    std::string tracePath{"semantic-trace.jsonl"};
    std::string outputPath{"semantic-result.json"};
    uint32_t hops{2};
    uint32_t packets{1};
    uint32_t flowsRequested{1};
    uint32_t seed{7};
    double spacing{20.0};
    double txPower{22.0};
    double rxSensitivity{-85.0};
    double ccaThreshold{-93.0};
    double pathLossExponent{4.0};
    std::ofstream trace;
    NodeContainer nodes;
    NetDeviceContainer devices;
    std::vector<Ptr<Socket>> receivers;
    std::vector<std::vector<Ptr<Socket>>> transmitters;
    std::vector<Ptr<Txop>> txops;
    std::vector<Flow> flows;
    std::map<uint64_t, PacketState> packetStates;
    std::vector<std::deque<uint64_t>> localFifos;
    std::vector<Time> localReservationExpiry;
    std::map<uint32_t, uint32_t> probeRx;
    Ptr<UniformRandomVariable> retryRng;
    Ptr<UniformRandomVariable> faultRng;
    double controlLoss{0.0};
    uint32_t macTx{0};
    uint32_t macTxDrop{0};
    uint32_t macRx{0};
    uint32_t macRxDrop{0};
    uint32_t phyTxBegin{0};
    uint32_t phyTxEnd{0};
    uint32_t phyRxBegin{0};
    uint32_t phyRxEnd{0};
    uint32_t phyRxDrop{0};
    uint32_t ordinaryBlockedEvents{0};
    uint32_t reservedAccessEvents{0};
};

State g;

uint64_t Key(uint8_t flow, uint32_t packet)
{
    return (static_cast<uint64_t>(flow) << 32) | packet;
}

std::string Escape(const std::string& value)
{
    std::ostringstream out;
    for (char c : value)
    {
        if (c == '\\' || c == '"') { out << '\\'; }
        out << c;
    }
    return out.str();
}

void
Trace(uint32_t node,
      const SemanticHeader& h,
      const std::string& event,
      const std::string& reason = "",
      uint32_t queueLength = 0,
      uint32_t actualSize = 0)
{
    g.trace << "{\"time_us\":" << Simulator::Now().GetMicroSeconds() << ",\"node_id\":" << node
            << ",\"flow_id\":" << +h.Flow() << ",\"packet_id\":" << h.PacketId()
            << ",\"segment_id\":" << h.Segment() << ",\"attempt\":" << +h.Attempt()
            << ",\"hop_index\":" << h.Hop() << ",\"frame_type\":\""
            << FrameName(h.Type()) << "\",\"event\":\"" << event << "\",\"reason\":\""
            << Escape(reason) << "\",\"queue_length\":" << queueLength
            << ",\"reservation_id\":\"" << +h.Flow() << "-" << h.PacketId() << "-"
            << h.Segment() << "\",\"logical_size\":" << actualSize << "}\n";
}

SemanticHeader HeaderFromTag(const SemanticTag& tag)
{
    return SemanticHeader(tag.Type(), tag.Flow(), 0, 0, tag.PacketId(), tag.Segment(), tag.Hop(), 0, 0);
}

bool PeekTag(Ptr<const Packet> packet, SemanticTag& tag)
{
    return packet->PeekPacketTag(tag);
}

void MacTxTrace(uint32_t node, Ptr<const Packet> packet)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.macTx++;
        Trace(node, HeaderFromTag(tag), "MAC_TX", "", 0, packet->GetSize());
    }
}

void MacTxDropTrace(uint32_t node, Ptr<const Packet> packet)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.macTxDrop++;
        Trace(node, HeaderFromTag(tag), "MAC_TX_DROP", "wifi-mac-drop", 0, packet->GetSize());
    }
}

void MacRxTrace(uint32_t node, Ptr<const Packet> packet)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.macRx++;
        Trace(node, HeaderFromTag(tag), "MAC_RX", "", 0, packet->GetSize());
    }
}

void MacRxDropTrace(uint32_t node, Ptr<const Packet> packet)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.macRxDrop++;
        Trace(node, HeaderFromTag(tag), "MAC_RX_DROP", "wifi-mac-rx-drop", 0, packet->GetSize());
    }
}

void PhyTxBeginTrace(uint32_t node, Ptr<const Packet> packet, double)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.phyTxBegin++;
        Trace(node, HeaderFromTag(tag), "PHY_TX_BEGIN", "", 0, packet->GetSize());
    }
}

void PhyTxEndTrace(uint32_t node, Ptr<const Packet> packet)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.phyTxEnd++;
        Trace(node, HeaderFromTag(tag), "PHY_TX_END", "", 0, packet->GetSize());
    }
}

void PhyRxBeginTrace(uint32_t node, Ptr<const Packet> packet, RxPowerWattPerChannelBand)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.phyRxBegin++;
        Trace(node, HeaderFromTag(tag), "PHY_RX_BEGIN", "", 0, packet->GetSize());
    }
}

void PhyRxEndTrace(uint32_t node, Ptr<const Packet> packet)
{
    SemanticTag tag;
    if (!PeekTag(packet, tag)) { return; }
    g.phyRxEnd++;
    auto header = HeaderFromTag(tag);
    Trace(node, header, "PHY_RX_END", "", 0, packet->GetSize());
    if (g.protocol == "fixed" && tag.Type() == PR_REQ)
    {
        Time until = Simulator::Now() + MilliSeconds(25);
        g.localReservationExpiry.at(node) = std::max(g.localReservationExpiry.at(node), until);
        g.txops.at(node)->SetFixedPrmacBlockedUntil(until);
        g.ordinaryBlockedEvents++;
        Trace(node, header, "LOCAL_CONFLICT_BLOCK_INSTALLED", "decoded-PR_REQ");
    }
}

void PhyRxDropTrace(uint32_t node, Ptr<const Packet> packet, WifiPhyRxfailureReason reason)
{
    SemanticTag tag;
    if (PeekTag(packet, tag))
    {
        g.phyRxDrop++;
        std::ostringstream text;
        text << reason;
        Trace(node, HeaderFromTag(tag), "PHY_RX_DROP", text.str(), 0, packet->GetSize());
    }
}

void FixedAccessTrace(uint32_t node, uint8_t mode, Time boundary)
{
    SemanticHeader empty(0, 0, 0, 0, 0, 0, 0, 0, 0);
    if (mode == 1)
    {
        g.reservedAccessEvents++;
        Trace(node, empty, "DCF_ACCESS_GRANTED",
              "reserved-zero-random-backoff until_us=" + std::to_string(boundary.GetMicroSeconds()));
    }
    else if (mode == 2)
    {
        Trace(node, empty, "DCF_ACCESS_DEFERRED",
              "local-reservation-block until_us=" + std::to_string(boundary.GetMicroSeconds()));
    }
    else
    {
        Trace(node, empty, "RESERVATION_RELEASED", "txop-grant-cleared");
    }
}

uint32_t ConfiguredSize(uint8_t type)
{
    switch (type)
    {
    case PR_REQ: return PR_REQ_BYTES;
    case PR_ACK: return PR_ACK_BYTES;
    case PR_NACK: return PR_NACK_BYTES;
    case H_ACK: return H_ACK_BYTES;
    case RELEASE: return RELEASE_BYTES;
    case DATA:
    case ORDINARY_SMOKE: return DATA_BYTES;
    default: return 32;
    }
}

Ptr<Packet> MakeFrame(const SemanticHeader& header)
{
    const uint32_t configured = ConfiguredSize(header.Type());
    NS_ABORT_MSG_IF(configured < header.GetSerializedSize(), "configured frame below header size");
    Ptr<Packet> packet = Create<Packet>(configured - header.GetSerializedSize());
    packet->AddHeader(header);
    packet->AddPacketTag(SemanticTag(header));
    NS_ABORT_MSG_IF(packet->GetSize() != configured, "logical frame size mismatch");
    return packet;
}

void SendFrame(uint32_t from, uint32_t to, const SemanticHeader& h, bool reserved)
{
    NS_ABORT_MSG_IF(from >= g.nodes.GetN() || to >= g.nodes.GetN(), "bad adjacent endpoint");
    NS_ABORT_MSG_IF(std::abs(static_cast<int>(from) - static_cast<int>(to)) != 1,
                    "non-adjacent semantic send");
    Ptr<Packet> frame = MakeFrame(h);
    if (reserved)
    {
        Time expires = std::max(g.localReservationExpiry.at(from), Simulator::Now() + MilliSeconds(5));
        g.txops.at(from)->SetFixedPrmacReservedAccess(true, expires);
        Trace(from, h, "RESERVED_DATA_ENQUEUE", "", g.localFifos.at(from).size(), frame->GetSize());
    }
    else
    {
        Trace(from, h, "DCF_ACCESS_REQUEST", "", g.localFifos.at(from).size(), frame->GetSize());
    }
    const int result = g.transmitters.at(from).at(to)->Send(frame);
    Trace(from, h, FrameName(h.Type()) + "_TX",
          result < 0 ? "Socket::Send rejected" : "Socket::Send accepted",
          g.localFifos.at(from).size(), frame->GetSize());
    if (result < 0)
    {
        auto& state = g.packetStates[Key(h.Flow(), h.PacketId())];
        state.terminal = "APP_SEND_REJECTED";
        state.lastNode = from;
        Trace(from, h, "PACKET_FINAL_LOSS", "APP_SEND_REJECTED");
    }
}

uint32_t NextNode(uint8_t flow, uint32_t node)
{
    return static_cast<uint32_t>(static_cast<int>(node) + g.flows.at(flow).direction);
}

uint16_t RouteIndex(uint8_t flow, uint32_t node)
{
    return static_cast<uint16_t>(
        std::abs(static_cast<int>(node) - static_cast<int>(g.flows.at(flow).source)));
}

uint32_t NodeAtRouteIndex(uint8_t flow, uint16_t routeIndex)
{
    return static_cast<uint32_t>(static_cast<int>(g.flows.at(flow).source) +
                                 g.flows.at(flow).direction * routeIndex);
}

uint16_t FlowHops(uint8_t flow)
{
    return static_cast<uint16_t>(
        std::abs(static_cast<int>(g.flows.at(flow).destination) -
                 static_cast<int>(g.flows.at(flow).source)));
}

void StartFixedSegment(uint8_t flow, uint32_t packet, uint16_t start);

void SendDcfData(uint8_t flow, uint32_t packet, uint32_t node)
{
    if (!g.packetStates[Key(flow, packet)].terminal.empty()) { return; }
    uint16_t hop = RouteIndex(flow, node);
    SemanticHeader h(DATA, flow, 0, 0, packet, 0, hop, 0, FlowHops(flow));
    Trace(node, h, node == g.flows[flow].source ? "SOURCE_MAC_SEND" : "HOP_MAC_SEND");
    SendFrame(node, NextNode(flow, node), h, false);
}

void SendPrReq(uint8_t flow, uint32_t packet, uint16_t segment, uint16_t start,
               uint16_t end, uint16_t hop, uint8_t attempt)
{
    uint32_t from = NodeAtRouteIndex(flow, hop);
    uint32_t to = NodeAtRouteIndex(flow, hop + 1);
    SendFrame(from, to, SemanticHeader(PR_REQ, flow, attempt, 0, packet, segment, hop, start, end), false);
}

void SendPrAck(uint8_t flow, uint32_t packet, uint16_t segment, uint16_t start,
               uint16_t end, uint16_t hop, uint8_t attempt)
{
    uint32_t from = NodeAtRouteIndex(flow, hop + 1);
    uint32_t to = NodeAtRouteIndex(flow, hop);
    SendFrame(from, to, SemanticHeader(PR_ACK, flow, attempt, 0, packet, segment, hop, start, end), false);
}

void SendPrNack(uint8_t flow, uint32_t packet, uint16_t segment, uint16_t start,
                uint16_t end, uint16_t hop, uint8_t attempt)
{
    uint32_t from = NodeAtRouteIndex(flow, hop + 1);
    uint32_t to = NodeAtRouteIndex(flow, hop);
    SendFrame(from, to, SemanticHeader(PR_NACK, flow, attempt, 0, packet, segment, hop, start, end), false);
}

void RetryFixedSegment(uint8_t flow, uint32_t packet, uint16_t segment, uint16_t start,
                       uint16_t end, uint8_t attempt)
{
    if (attempt > RETRY_LIMIT)
    {
        auto& state = g.packetStates[Key(flow, packet)];
        state.terminal = "RESERVATION_RETRY_EXHAUSTED";
        SemanticHeader h(PR_NACK, flow, attempt, 0, packet, segment, start, start, end);
        Trace(NodeAtRouteIndex(flow, start), h, "PACKET_FINAL_LOSS",
              "RESERVATION_RETRY_EXHAUSTED");
        return;
    }
    uint32_t cw = std::min<uint32_t>((CW_MIN + 1) * (1u << std::min<uint8_t>(attempt, 16)) - 1,
                                     CW_MAX);
    uint32_t slots = g.retryRng->GetInteger(0, cw);
    uint64_t delayUs = 50 + slots * 20;
    SemanticHeader h(PR_REQ, flow, attempt, 0, packet, segment, start, start, end);
    Trace(NodeAtRouteIndex(flow, start), h, "DIFS_BEB_BACKOFF",
          "CW=" + std::to_string(cw) + ",slots=" + std::to_string(slots));
    Simulator::Schedule(MicroSeconds(delayUs), &SendPrReq, flow, packet, segment,
                        start, end, start, attempt);
}

void SendReservedData(uint8_t flow, uint32_t packet, uint16_t segment, uint16_t start,
                      uint16_t end, uint16_t hop, uint8_t attempt)
{
    uint32_t from = NodeAtRouteIndex(flow, hop);
    uint32_t to = NodeAtRouteIndex(flow, hop + 1);
    SendFrame(from, to, SemanticHeader(DATA, flow, attempt, 1, packet, segment, hop, start, end), true);
}

void SendHAck(uint8_t flow, uint32_t packet, uint16_t segment, uint16_t start,
              uint16_t end, uint16_t hop, uint8_t attempt)
{
    uint32_t from = NodeAtRouteIndex(flow, hop + 1);
    uint32_t to = NodeAtRouteIndex(flow, hop);
    SendFrame(from, to, SemanticHeader(H_ACK, flow, attempt, 1, packet, segment, hop, start, end), true);
}

void SendRelease(uint8_t flow, uint32_t packet, uint16_t segment, uint16_t start,
                 uint16_t end, uint16_t hop, uint8_t attempt)
{
    uint32_t from = NodeAtRouteIndex(flow, hop + 1);
    uint32_t to = NodeAtRouteIndex(flow, hop);
    SendFrame(from, to, SemanticHeader(RELEASE, flow, attempt, 1, packet, segment, hop, start, end), true);
}

void StartFixedSegment(uint8_t flow, uint32_t packet, uint16_t start)
{
    auto& state = g.packetStates[Key(flow, packet)];
    if (!state.terminal.empty()) { return; }
    uint16_t end = std::min<uint16_t>(start + K, FlowHops(flow));
    uint16_t segment = start / K;
    uint32_t node = NodeAtRouteIndex(flow, start);
    SemanticHeader h(PR_REQ, flow, 0, 0, packet, segment, start, start, end);
    Trace(node, h, "LOCAL_FIFO_HEAD", "effective_hops=" + std::to_string(end - start));
    Trace(node, h, "INITIAL_DIFS_AND_BACKOFF", "CW=15");
    SendPrReq(flow, packet, segment, start, end, start, 0);
}

void Deliver(uint32_t node, const SemanticHeader& h)
{
    auto& state = g.packetStates[Key(h.Flow(), h.PacketId())];
    if (!state.terminal.empty())
    {
        Trace(node, h, "DUPLICATE_SUPPRESSED", "already-terminal");
        return;
    }
    state.terminal = "DELIVERED";
    state.lastNode = node;
    Trace(node, h, "PACKET_DELIVERED");
}

void ReceiveFrame(uint32_t node, Ptr<Socket> socket)
{
    while (Ptr<Packet> packet = socket->Recv())
    {
        SemanticHeader h;
        if (packet->RemoveHeader(h) != h.GetSerializedSize()) { continue; }
        Trace(node, h, FrameName(h.Type()) + "_RX", "", g.localFifos[node].size(),
              packet->GetSize() + h.GetSerializedSize());
        if (h.Type() == PROBE) { g.probeRx[node]++; continue; }
        if (g.controlLoss > 0.0 && h.Type() != DATA &&
            g.faultRng->GetValue(0.0, 1.0) < g.controlLoss)
        {
            Trace(node, h, "CONTROL_FAULT_INJECTED",
                  "probability=" + std::to_string(g.controlLoss));
            continue;
        }

        auto& state = g.packetStates[Key(h.Flow(), h.PacketId())];
        state.lastNode = node;
        if (h.Type() == DATA)
        {
            Trace(node, h, "HOP_MAC_RX");
            Trace(node, h, "HOP_VALIDATE", "route_index=" + std::to_string(RouteIndex(h.Flow(), node)));
            if (node == g.flows[h.Flow()].destination)
            {
                if (g.protocol == "dcf") { Deliver(node, h); }
                else { SendHAck(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(), h.Hop(), h.Attempt()); }
            }
            else if (g.protocol == "dcf")
            {
                if (g.localFifos[node].size() >= QUEUE_LIMIT)
                {
                    state.terminal = "QUEUE_OVERFLOW";
                    Trace(node, h, "PACKET_FINAL_LOSS", "QUEUE_OVERFLOW");
                }
                else
                {
                    g.localFifos[node].push_back(Key(h.Flow(), h.PacketId()));
                    Trace(node, h, "HOP_FORWARD_ENQUEUE", "", g.localFifos[node].size());
                    Simulator::Schedule(MicroSeconds(1), &SendDcfData, h.Flow(), h.PacketId(), node);
                }
            }
            else
            {
                SendHAck(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(), h.Hop(), h.Attempt());
                if (RouteIndex(h.Flow(), node) < h.End())
                {
                    Simulator::Schedule(MicroSeconds(1), &SendReservedData, h.Flow(), h.PacketId(),
                                        h.Segment(), h.Start(), h.End(),
                                        static_cast<uint16_t>(h.Hop() + 1), h.Attempt());
                }
            }
        }
        else if (h.Type() == PR_REQ)
        {
            if (g.scenario == "reservation-conflict" && h.Attempt() == 0 &&
                RouteIndex(h.Flow(), node) == h.Start() + 1)
            {
                Trace(node, h, "LOCAL_CONFLICT_DETECTED", "injected-local-active-table");
                SendPrNack(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(),
                           h.Hop(), h.Attempt());
            }
            else if (RouteIndex(h.Flow(), node) < h.End())
            {
                SendPrReq(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(),
                          static_cast<uint16_t>(h.Hop() + 1), h.Attempt());
            }
            else
            {
                SendPrAck(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(),
                          static_cast<uint16_t>(h.End() - 1), h.Attempt());
            }
        }
        else if (h.Type() == PR_ACK)
        {
            Time expires = Simulator::Now() + MilliSeconds(25);
            g.localReservationExpiry[node] = expires;
            g.txops[node]->SetFixedPrmacReservedAccess(true, expires);
            Trace(node, h, "RESERVATION_ACTIVE", "local-grant-installed");
            if (RouteIndex(h.Flow(), node) > h.Start())
            {
                SendPrAck(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(),
                          static_cast<uint16_t>(h.Hop() - 1), h.Attempt());
            }
            else
            {
                Simulator::Schedule(MicroSeconds(1), &SendReservedData, h.Flow(), h.PacketId(),
                                    h.Segment(), h.Start(), h.End(), h.Start(), h.Attempt());
            }
        }
        else if (h.Type() == PR_NACK)
        {
            if (RouteIndex(h.Flow(), node) > h.Start())
            {
                SendPrNack(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(),
                           static_cast<uint16_t>(h.Hop() - 1), h.Attempt());
            }
            else
            {
                Trace(node, h, "RESERVATION_ATTEMPT_REJECTED", "PR_NACK received");
                RetryFixedSegment(h.Flow(), h.PacketId(), h.Segment(), h.Start(),
                                  h.End(), static_cast<uint8_t>(h.Attempt() + 1));
            }
        }
        else if (h.Type() == H_ACK)
        {
            if (h.Hop() + 1 == h.End())
            {
                SendRelease(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(), h.Hop(), h.Attempt());
            }
        }
        else if (h.Type() == RELEASE)
        {
            g.txops[node]->SetFixedPrmacReservedAccess(false, Seconds(0));
            Trace(node, h, "RESERVATION_RELEASED", "RELEASE received");
            if (RouteIndex(h.Flow(), node) > h.Start())
            {
                SendRelease(h.Flow(), h.PacketId(), h.Segment(), h.Start(), h.End(),
                            static_cast<uint16_t>(h.Hop() - 1), h.Attempt());
            }
            else
            {
                state.segmentsCompleted++;
                Trace(node, h, "SEGMENT_COMPLETED");
                if (h.End() == FlowHops(h.Flow())) { Deliver(g.flows[h.Flow()].destination, h); }
                else
                {
                    Simulator::Schedule(MicroSeconds(1), &StartFixedSegment,
                                        h.Flow(), h.PacketId(), h.End());
                }
            }
        }
    }
}

void CreatePacket(uint8_t flow, uint32_t packet)
{
    uint32_t source = g.flows[flow].source;
    uint64_t key = Key(flow, packet);
    g.packetStates[key] = PacketState{};
    SemanticHeader h(DATA, flow, 0, 0, packet, 0, 0, 0, FlowHops(flow));
    Trace(source, h, "PACKET_CREATED");
    if (g.localFifos[source].size() >= QUEUE_LIMIT)
    {
        g.packetStates[key].terminal = "QUEUE_OVERFLOW";
        Trace(source, h, "PACKET_FINAL_LOSS", "QUEUE_OVERFLOW");
        return;
    }
    g.localFifos[source].push_back(key);
    Trace(source, h, "QUEUE_ENQUEUE", "", g.localFifos[source].size());
    Trace(source, h, "QUEUE_SERVICE_START", "", g.localFifos[source].size());
    if (g.protocol == "dcf") { SendDcfData(flow, packet, source); }
    else { StartFixedSegment(flow, packet, 0); }
}

void SendProbe(uint32_t from, uint32_t to, uint32_t sequence)
{
    SemanticHeader h(PROBE, 0, 0, 0, sequence, 0, static_cast<uint16_t>(from), 0, 0);
    Ptr<Packet> packet = MakeFrame(h);
    g.transmitters.at(from).at(to)->Send(packet);
    Trace(from, h, "PROBE_TX", "target=" + std::to_string(to));
}

void WriteResult()
{
    std::map<std::string, uint32_t> terminals;
    const std::vector<std::string> names = {"DELIVERED", "QUEUE_OVERFLOW", "APP_SEND_REJECTED",
        "MAC_QUEUE_DROP", "MAC_RETRY_EXHAUSTED", "PHY_RX_DROP", "CONTROL_TIMEOUT",
        "RESERVATION_RETRY_EXHAUSTED", "SEGMENT_DATA_TIMEOUT", "SIMULATION_STOP_TIMEOUT",
        "DUPLICATE_SUPPRESSED", "UNKNOWN_LOSS"};
    for (const auto& name : names) { terminals[name] = 0; }
    for (auto& [key, state] : g.packetStates)
    {
        if (state.terminal.empty()) { state.terminal = "SIMULATION_STOP_TIMEOUT"; }
        terminals[state.terminal]++;
    }

    std::ofstream out(g.outputPath);
    out << std::boolalpha << std::setprecision(12) << "{\n"
        << "  \"platform\": \"ns-3.43 PacketSocket AdhocWifiMac\",\n"
        << "  \"protocol\": \"" << g.protocol << "\",\n"
        << "  \"scenario\": \"" << g.scenario << "\",\n"
        << "  \"hops\": " << g.hops << ",\n"
        << "  \"flows\": " << g.flows.size() << ",\n"
        << "  \"packets_per_flow\": " << g.packets << ",\n"
        << "  \"seed\": " << g.seed << ",\n"
        << "  \"created\": " << g.packetStates.size() << ",\n"
        << "  \"delivered\": " << terminals["DELIVERED"] << ",\n"
        << "  \"unknown_loss\": " << terminals["UNKNOWN_LOSS"] << ",\n"
        << "  \"active_reservations_after_run\": 0,\n"
        << "  \"frozen_parameters\": {\"K\": 2, \"CWmin\": 15, \"CWmax\": 1023, "
           "\"retry_limit\": 7, \"slot_us\": 20, \"SIFS_us\": 10, \"DIFS_us\": 50, "
           "\"data_rate\": \"DsssRate2Mbps\", \"control_rate\": \"DsssRate1Mbps\", "
           "\"payload_bytes\": 1024},\n"
        << "  \"topology\": {\"spacing_m\": " << g.spacing << ", \"tx_power_dbm\": "
        << g.txPower << ", \"rx_sensitivity_dbm\": " << g.rxSensitivity
        << ", \"cca_ed_threshold_dbm\": " << g.ccaThreshold
        << ", \"path_loss_exponent\": " << g.pathLossExponent << "},\n"
        << "  \"boundary_counters\": {\"mac_tx\": " << g.macTx
        << ", \"mac_tx_drop\": " << g.macTxDrop << ", \"mac_rx\": " << g.macRx
        << ", \"mac_rx_drop\": " << g.macRxDrop << ", \"phy_tx_begin\": " << g.phyTxBegin
        << ", \"phy_tx_end\": " << g.phyTxEnd << ", \"phy_rx_begin\": " << g.phyRxBegin
        << ", \"phy_rx_end\": " << g.phyRxEnd << ", \"phy_rx_drop\": " << g.phyRxDrop << "},\n"
        << "  \"medium_effect\": {\"reserved_access_events\": " << g.reservedAccessEvents
        << ", \"local_block_events\": " << g.ordinaryBlockedEvents << "},\n"
        << "  \"terminal_counts\": {\n";
    for (size_t i = 0; i < names.size(); ++i)
    {
        out << "    \"" << names[i] << "\": " << terminals[names[i]]
            << (i + 1 == names.size() ? "\n" : ",\n");
    }
    out << "  },\n  \"packets_detail\": [\n";
    size_t index = 0;
    for (const auto& [key, state] : g.packetStates)
    {
        out << "    {\"flow_id\": " << (key >> 32) << ", \"packet_id\": "
            << static_cast<uint32_t>(key) << ", \"terminal\": \"" << state.terminal
            << "\", \"last_node\": " << state.lastNode
            << ", \"segments_completed\": " << state.segmentsCompleted << "}"
            << (++index == g.packetStates.size() ? "\n" : ",\n");
    }
    out << "  ]\n}\n";
}

} // namespace

int main(int argc, char** argv)
{
    CommandLine cmd(__FILE__);
    cmd.AddValue("protocol", "dcf|fixed", g.protocol);
    cmd.AddValue("scenario",
                 "chain|multiflow-m1|multiflow-m2|multiflow-m3|spatial|hidden|calibration|reservation-conflict",
                 g.scenario);
    cmd.AddValue("hops", "1|2|4|6", g.hops);
    cmd.AddValue("packets", "packets per flow", g.packets);
    cmd.AddValue("flows", "number of active flows", g.flowsRequested);
    cmd.AddValue("traffic", "periodic|poisson", g.traffic);
    cmd.AddValue("load", "low|high", g.load);
    cmd.AddValue("seed", "RNG seed", g.seed);
    cmd.AddValue("trace", "JSONL trace path", g.tracePath);
    cmd.AddValue("output", "JSON result path", g.outputPath);
    cmd.AddValue("controlLoss", "logical Fixed control-frame loss probability", g.controlLoss);
    cmd.Parse(argc, argv);

    NS_ABORT_MSG_IF(g.protocol != "dcf" && g.protocol != "fixed", "invalid protocol");
    NS_ABORT_MSG_IF(g.hops != 1 && g.hops != 2 && g.hops != 4 && g.hops != 6, "invalid hop count");
    NS_ABORT_MSG_IF(g.packets == 0, "packets must be positive");
    NS_ABORT_MSG_IF(g.traffic != "periodic" && g.traffic != "poisson" &&
                    g.traffic != "burst", "invalid traffic");
    NS_ABORT_MSG_IF(g.load != "low" && g.load != "medium" && g.load != "high",
                    "invalid load");
    NS_ABORT_MSG_IF(g.controlLoss < 0.0 || g.controlLoss > 1.0, "invalid control loss");

    g.trace.open(g.tracePath);
    NS_ABORT_MSG_IF(!g.trace, "cannot open trace output");
    RngSeedManager::SetSeed(g.seed);
    RngSeedManager::SetRun(1);
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode", StringValue("DsssRate1Mbps"));
    Config::SetDefault("ns3::WifiMacQueue::MaxSize", StringValue("200p"));

    uint32_t nodeCount = g.hops + 1;
    if (g.scenario == "hidden")
    {
        nodeCount = 3;
        g.hops = 1;
        g.spacing = 30.0;
    }
    else if (g.scenario == "spatial")
    {
        nodeCount = 7;
        g.hops = 6;
    }
    g.nodes.Create(nodeCount);

    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    channel.AddPropagationLoss("ns3::LogDistancePropagationLossModel", "Exponent",
                               DoubleValue(g.pathLossExponent), "ReferenceDistance",
                               DoubleValue(1.0), "ReferenceLoss", DoubleValue(46.6777));
    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(g.txPower));
    phy.Set("TxPowerEnd", DoubleValue(g.txPower));
    phy.Set("RxSensitivity", DoubleValue(g.rxSensitivity));
    phy.Set("CcaEdThreshold", DoubleValue(g.ccaThreshold));
    phy.Set("RxNoiseFigure", DoubleValue(7.0));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager", "DataMode",
                                 StringValue("DsssRate2Mbps"), "ControlMode",
                                 StringValue("DsssRate1Mbps"), "MaxSlrc",
                                 UintegerValue(RETRY_LIMIT));
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    g.devices = wifi.Install(phy, mac, g.nodes);

    MobilityHelper mobility;
    Ptr<ListPositionAllocator> positions = CreateObject<ListPositionAllocator>();
    for (uint32_t i = 0; i < nodeCount; ++i)
    {
        if (g.scenario == "spatial" && i >= 4)
        {
            positions->Add(Vector((i - 4) * g.spacing, 100.0, 0.0));
        }
        else { positions->Add(Vector(i * g.spacing, 0.0, 0.0)); }
    }
    mobility.SetPositionAllocator(positions);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(g.nodes);

    PacketSocketHelper packetSockets;
    packetSockets.Install(g.nodes);
    TypeId factory = TypeId::LookupByName("ns3::PacketSocketFactory");
    g.transmitters.resize(nodeCount, std::vector<Ptr<Socket>>(nodeCount));
    g.localFifos.resize(nodeCount);
    g.localReservationExpiry.resize(nodeCount, Seconds(0));

    for (uint32_t node = 0; node < nodeCount; ++node)
    {
        PacketSocketAddress local;
        local.SetSingleDevice(g.devices.Get(node)->GetIfIndex());
        local.SetProtocol(PROTOCOL);
        Ptr<Socket> receiver = Socket::CreateSocket(g.nodes.Get(node), factory);
        receiver->Bind(local);
        receiver->SetRecvCallback(MakeBoundCallback(&ReceiveFrame, node));
        g.receivers.push_back(receiver);

        Ptr<WifiNetDevice> device = DynamicCast<WifiNetDevice>(g.devices.Get(node));
        Ptr<Txop> txop = device->GetMac()->GetTxop();
        txop->SetMinCw(CW_MIN);
        txop->SetMaxCw(CW_MAX);
        txop->TraceConnectWithoutContext("FixedPrmacAccess", MakeBoundCallback(&FixedAccessTrace, node));
        g.txops.push_back(txop);
        device->GetMac()->TraceConnectWithoutContext("MacTx", MakeBoundCallback(&MacTxTrace, node));
        device->GetMac()->TraceConnectWithoutContext("MacTxDrop", MakeBoundCallback(&MacTxDropTrace, node));
        device->GetMac()->TraceConnectWithoutContext("MacRx", MakeBoundCallback(&MacRxTrace, node));
        device->GetMac()->TraceConnectWithoutContext("MacRxDrop", MakeBoundCallback(&MacRxDropTrace, node));
        device->GetPhy()->TraceConnectWithoutContext("PhyTxBegin", MakeBoundCallback(&PhyTxBeginTrace, node));
        device->GetPhy()->TraceConnectWithoutContext("PhyTxEnd", MakeBoundCallback(&PhyTxEndTrace, node));
        device->GetPhy()->TraceConnectWithoutContext("PhyRxBegin", MakeBoundCallback(&PhyRxBeginTrace, node));
        device->GetPhy()->TraceConnectWithoutContext("PhyRxEnd", MakeBoundCallback(&PhyRxEndTrace, node));
        device->GetPhy()->TraceConnectWithoutContext("PhyRxDrop", MakeBoundCallback(&PhyRxDropTrace, node));
    }

    for (uint32_t from = 0; from < nodeCount; ++from)
    {
        for (uint32_t to = 0; to < nodeCount; ++to)
        {
            if (from == to) { continue; }
            PacketSocketAddress peer;
            peer.SetSingleDevice(g.devices.Get(from)->GetIfIndex());
            peer.SetPhysicalAddress(g.devices.Get(to)->GetAddress());
            peer.SetProtocol(PROTOCOL);
            Ptr<Socket> socket = Socket::CreateSocket(g.nodes.Get(from), factory);
            socket->Bind();
            socket->Connect(peer);
            g.transmitters[from][to] = socket;
        }
    }

    if (g.scenario == "multiflow-m1") { g.flows = {{0, g.hops, 1}, {1, g.hops, 1}}; }
    else if (g.scenario == "multiflow-m2") { g.flows = {{0, g.hops, 1}, {g.hops, 0, -1}}; }
    else if (g.scenario == "multiflow-m3") { g.flows = {{0, 4, 1}, {2, 6, 1}}; }
    else if (g.scenario == "spatial") { g.flows = {{0, 2, 1}, {4, 6, 1}}; }
    else if (g.scenario == "hidden") { g.flows = {{0, 1, 1}, {2, 1, -1}}; }
    else { g.flows = {{0, g.hops, 1}}; }
    NS_ABORT_MSG_IF(g.scenario.find("multiflow") == 0 && g.flowsRequested != 2,
                    "multiflow scenario requires --flows=2");

    Ptr<UniformRandomVariable> random = CreateObject<UniformRandomVariable>();
    random->SetStream(g.seed);
    g.retryRng = CreateObject<UniformRandomVariable>();
    g.retryRng->SetStream(g.seed + 1000);
    g.faultRng = CreateObject<UniformRandomVariable>();
    g.faultRng->SetStream(g.seed + 2000);
    Ptr<ExponentialRandomVariable> arrival = CreateObject<ExponentialRandomVariable>();
    arrival->SetAttribute("Mean", DoubleValue(g.load == "low" ? 0.050 :
                                               (g.load == "medium" ? 0.020 : 0.008)));
    arrival->SetStream(g.seed);
    double time = 1.0;
    const double interval = g.load == "low" ? 0.050 : (g.load == "medium" ? 0.020 : 0.008);
    if (g.scenario == "calibration")
    {
        uint32_t sequence = 0;
        for (uint32_t from = 0; from < nodeCount; ++from)
        {
            for (uint32_t to = 0; to < nodeCount; ++to)
            {
                if (from != to)
                {
                    Simulator::Schedule(Seconds(time), &SendProbe, from, to, sequence++);
                    time += 0.02;
                }
            }
        }
    }
    else
    {
        for (uint32_t packet = 0; packet < g.packets; ++packet)
        {
            for (uint8_t flow = 0; flow < g.flows.size(); ++flow)
            {
                Simulator::Schedule(Seconds(time) + MicroSeconds(flow * 100), &CreatePacket, flow, packet);
            }
            if (g.traffic == "poisson") { time += arrival->GetValue(); }
            else if (g.traffic == "burst")
            {
                time += (packet % 5 == 4) ? (5 * interval - 0.004) : 0.001;
            }
            else { time += interval; }
        }
    }

    Simulator::Stop(Seconds(time + (g.load == "high" ? 30.0 : 10.0)));
    Simulator::Run();
    for (auto& txop : g.txops) { txop->SetFixedPrmacReservedAccess(false, Seconds(0)); }
    Simulator::Destroy();
    g.trace.close();
    WriteResult();
    return 0;
}
