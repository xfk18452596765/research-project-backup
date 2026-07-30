#include "ns3/command-line.h"
#include "ns3/config.h"
#include "ns3/double.h"
#include "ns3/internet-stack-helper.h"
#include "ns3/ipv4-address-helper.h"
#include "ns3/mobility-helper.h"
#include "ns3/network-module.h"
#include "ns3/rng-seed-manager.h"
#include "ns3/socket.h"
#include "ns3/string.h"
#include "ns3/uinteger.h"
#include "ns3/wifi-module.h"
#include "ns3/yans-wifi-channel.h"
#include "ns3/yans-wifi-helper.h"

#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

namespace {

constexpr uint32_t K = 2;
constexpr uint32_t CW_MIN = 15;
constexpr uint32_t CW_MAX = 1023;
constexpr uint32_t RETRY_LIMIT = 7;
constexpr uint32_t PAYLOAD_BYTES = 1024;
constexpr uint32_t DATA_RATE_MBPS = 2;
constexpr uint32_t CONTROL_RATE_MBPS = 1;
constexpr uint32_t SLOT_US = 20;

class DiagnosticHeader : public Header
{
  public:
    DiagnosticHeader() = default;
    DiagnosticHeader(uint32_t seq, uint16_t hop)
        : m_seq(seq),
          m_hop(hop)
    {
    }
    static TypeId GetTypeId()
    {
        static TypeId tid =
            TypeId("DiagnosticHeader").SetParent<Header>().AddConstructor<DiagnosticHeader>();
        return tid;
    }
    TypeId GetInstanceTypeId() const override
    {
        return GetTypeId();
    }
    uint32_t GetSerializedSize() const override
    {
        return 6;
    }
    void Serialize(Buffer::Iterator start) const override
    {
        start.WriteHtonU32(m_seq);
        start.WriteHtonU16(m_hop);
    }
    uint32_t Deserialize(Buffer::Iterator start) override
    {
        m_seq = start.ReadNtohU32();
        m_hop = start.ReadNtohU16();
        return GetSerializedSize();
    }
    void Print(std::ostream& os) const override
    {
        os << "seq=" << m_seq << ",hop=" << m_hop;
    }
    uint32_t GetSeq() const
    {
        return m_seq;
    }
    uint16_t GetHop() const
    {
        return m_hop;
    }

  private:
    uint32_t m_seq{0};
    uint16_t m_hop{0};
};

class DiagnosticTag : public Tag
{
  public:
    DiagnosticTag() = default;
    DiagnosticTag(uint32_t seq, uint16_t hop)
        : m_seq(seq),
          m_hop(hop)
    {
    }
    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("DiagnosticTag").SetParent<Tag>().AddConstructor<DiagnosticTag>();
        return tid;
    }
    TypeId GetInstanceTypeId() const override
    {
        return GetTypeId();
    }
    uint32_t GetSerializedSize() const override
    {
        return 6;
    }
    void Serialize(TagBuffer buffer) const override
    {
        buffer.WriteU32(m_seq);
        buffer.WriteU16(m_hop);
    }
    void Deserialize(TagBuffer buffer) override
    {
        m_seq = buffer.ReadU32();
        m_hop = buffer.ReadU16();
    }
    void Print(std::ostream& os) const override
    {
        os << "seq=" << m_seq << ",hop=" << m_hop;
    }
    uint32_t GetSeq() const
    {
        return m_seq;
    }
    uint16_t GetHop() const
    {
        return m_hop;
    }

  private:
    uint32_t m_seq{0};
    uint16_t m_hop{0};
};

struct PacketState
{
    bool delivered{false};
    bool appRejected{false};
    bool macDrop{false};
    bool phyDrop{false};
    uint32_t terminalHop{0};
    uint32_t reservationSegments{0};
    uint32_t maxSegmentHops{0};
};

struct RunState
{
    std::string mode;
    std::string protocol;
    std::string load;
    std::string traffic;
    uint32_t hops{1};
    uint32_t packets{1};
    uint32_t seed{7};
    bool causal{false};
    bool positioned{false};
    bool k2{false};
    bool reservationWindow{false};
    std::ofstream trace;
    std::vector<Ptr<Socket>> dataTx;
    std::vector<Ptr<Socket>> controlTx;
    std::vector<PacketState> packetState;
    std::map<uint32_t, double> createdAt;
    uint32_t macEnqueue{0};
    uint32_t macDrop{0};
    uint32_t phyTx{0};
    uint32_t phyRx{0};
    uint32_t phyDrop{0};
};

RunState g;

std::string Escape(const std::string& value)
{
    std::ostringstream out;
    for (char c : value)
    {
        if (c == '\\' || c == '"')
        {
            out << '\\';
        }
        out << c;
    }
    return out.str();
}

void Trace(uint32_t seq, uint32_t hop, const std::string& event, const std::string& detail = "")
{
    g.trace << "{\"time_us\":" << Simulator::Now().GetMicroSeconds() << ",\"seq\":" << seq
            << ",\"hop\":" << hop << ",\"event\":\"" << event << "\"";
    if (!detail.empty())
    {
        g.trace << ",\"detail\":\"" << Escape(detail) << "\"";
    }
    g.trace << "}\n";
}

bool GetIdentity(Ptr<const Packet> packet, uint32_t& seq, uint32_t& hop)
{
    DiagnosticTag tag;
    if (!packet->PeekPacketTag(tag))
    {
        return false;
    }
    seq = tag.GetSeq();
    hop = tag.GetHop();
    return true;
}

void MacTx(Ptr<const Packet> packet)
{
    uint32_t seq;
    uint32_t hop;
    if (GetIdentity(packet, seq, hop))
    {
        g.macEnqueue++;
        Trace(seq, hop, "MAC_ENQUEUE");
    }
}

void MacTxDrop(Ptr<const Packet> packet)
{
    uint32_t seq;
    uint32_t hop;
    if (GetIdentity(packet, seq, hop) && seq < g.packetState.size())
    {
        g.macDrop++;
        g.packetState[seq].macDrop = true;
        g.packetState[seq].terminalHop = hop;
        Trace(seq, hop, "MAC_QUEUE_DROP");
    }
}

void PhyTxBegin(Ptr<const Packet> packet, double)
{
    uint32_t seq;
    uint32_t hop;
    if (GetIdentity(packet, seq, hop))
    {
        g.phyTx++;
        Trace(seq, hop, "PHY_TX");
    }
}

void PhyRxEnd(Ptr<const Packet> packet)
{
    uint32_t seq;
    uint32_t hop;
    if (GetIdentity(packet, seq, hop))
    {
        g.phyRx++;
        Trace(seq, hop, "PHY_RX");
    }
}

void PhyRxDrop(Ptr<const Packet> packet, WifiPhyRxfailureReason)
{
    uint32_t seq;
    uint32_t hop;
    if (GetIdentity(packet, seq, hop) && seq < g.packetState.size())
    {
        g.phyDrop++;
        g.packetState[seq].phyDrop = true;
        g.packetState[seq].terminalHop = hop;
        Trace(seq, hop, "PHY_RX_DROP");
    }
}

Ptr<Packet> MakePacket(uint32_t seq, uint32_t hop, uint32_t bytes)
{
    DiagnosticHeader header(seq, static_cast<uint16_t>(hop));
    Ptr<Packet> packet = Create<Packet>(bytes - header.GetSerializedSize());
    packet->AddHeader(header);
    packet->AddPacketTag(DiagnosticTag(seq, static_cast<uint16_t>(hop)));
    return packet;
}

void SendControl(uint32_t seq, uint32_t hop, uint32_t bytes, const std::string& name)
{
    Ptr<Packet> packet = MakePacket(seq, hop, bytes);
    const int sent = g.controlTx.at(hop)->Send(packet);
    Trace(seq, hop, name, sent < 0 ? "Socket::Send=-1" : "Socket::Send=" + std::to_string(sent));
}

void SendHop(uint32_t seq, uint32_t hop)
{
    if (seq >= g.packetState.size() || hop >= g.hops || g.packetState[seq].delivered)
    {
        return;
    }
    uint64_t dataDelayUs = 0;
    if (g.protocol == "fixed" && (!g.k2 || hop % K == 0))
    {
        SendControl(seq, hop, 36, "PR_REQ_SOCKET_SEND");
        Simulator::Schedule(MicroSeconds(320), &SendControl, seq, hop, 24, "PR_ACK_SOCKET_SEND");
        dataDelayUs = 540;
    }
    if (g.reservationWindow && g.protocol == "fixed")
    {
        dataDelayUs += (seq % 8) * 700;
    }
    Simulator::Schedule(MicroSeconds(dataDelayUs), [seq, hop]() {
        Ptr<Packet> packet = MakePacket(seq, hop, PAYLOAD_BYTES);
        Trace(seq, hop, "APP_SEND_ATTEMPT");
        const int sent = g.dataTx.at(hop)->Send(packet);
        if (sent < 0)
        {
            g.packetState[seq].appRejected = true;
            g.packetState[seq].terminalHop = hop;
            Trace(seq, hop, "APP_SEND_REJECTED");
        }
        else
        {
            Trace(seq, hop, "SOCKET_SEND_ACCEPTED", "bytes=" + std::to_string(sent));
        }
    });
}

void ReceiveData(Ptr<Socket> socket)
{
    while (Ptr<Packet> packet = socket->Recv())
    {
        DiagnosticHeader header;
        if (packet->RemoveHeader(header) != header.GetSerializedSize())
        {
            continue;
        }
        const uint32_t seq = header.GetSeq();
        const uint32_t hop = header.GetHop();
        Trace(seq, hop, "UDP_RX");
        if (seq >= g.packetState.size())
        {
            continue;
        }
        if (hop + 1 == g.hops)
        {
            g.packetState[seq].delivered = true;
            g.packetState[seq].terminalHop = g.hops;
        }
        else if (g.causal)
        {
            Simulator::Schedule(MicroSeconds(100), &SendHop, seq, hop + 1);
        }
    }
}

void DrainControl(Ptr<Socket> socket)
{
    while (Ptr<Packet> packet = socket->Recv())
    {
        uint32_t seq;
        uint32_t hop;
        if (GetIdentity(packet, seq, hop))
        {
            Trace(seq, hop, "CONTROL_UDP_RX");
        }
    }
}

} // namespace

int main(int argc, char** argv)
{
    std::string tracePath = "diagnostic-trace.jsonl";
    std::string outputPath = "diagnostic-output.json";
    g.mode = "original";
    g.protocol = "dcf";
    g.load = "single";
    g.traffic = "periodic";

    CommandLine cmd(__FILE__);
    cmd.AddValue("mode", "original|causal-forwarding|positioned-chain|k2-segment|reservation-window|combined-reference", g.mode);
    cmd.AddValue("protocol", "dcf|fixed", g.protocol);
    cmd.AddValue("hops", "1|2|4|6", g.hops);
    cmd.AddValue("packets", "packet count", g.packets);
    cmd.AddValue("load", "single|low|medium|high", g.load);
    cmd.AddValue("traffic", "periodic|poisson", g.traffic);
    cmd.AddValue("seed", "deterministic seed", g.seed);
    cmd.AddValue("trace", "JSONL trace path", tracePath);
    cmd.AddValue("output", "JSON summary path", outputPath);
    cmd.Parse(argc, argv);

    const std::set<std::string> modes = {"original",
                                         "causal-forwarding",
                                         "positioned-chain",
                                         "k2-segment",
                                         "reservation-window",
                                         "combined-reference"};
    if (!modes.count(g.mode) || (g.protocol != "dcf" && g.protocol != "fixed") ||
        (g.hops != 1 && g.hops != 2 && g.hops != 4 && g.hops != 6) || g.packets == 0)
    {
        NS_FATAL_ERROR("invalid diagnostic CLI");
    }
    g.causal = g.mode == "causal-forwarding" || g.mode == "combined-reference";
    g.positioned = g.mode == "positioned-chain" || g.mode == "combined-reference";
    g.k2 = g.mode == "k2-segment" || g.mode == "combined-reference";
    g.reservationWindow = g.mode == "reservation-window" || g.mode == "combined-reference";
    g.packetState.resize(g.packets);
    for (auto& state : g.packetState)
    {
        state.reservationSegments =
            g.protocol == "fixed" ? (g.k2 ? (g.hops + K - 1) / K : g.hops) : 0;
        state.maxSegmentHops = g.protocol == "fixed" ? (g.k2 ? std::min(K, g.hops) : 1) : 0;
    }
    g.trace.open(tracePath);
    if (!g.trace)
    {
        NS_FATAL_ERROR("cannot open trace");
    }

    RngSeedManager::SetSeed(g.seed);
    RngSeedManager::SetRun(1);
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode",
                       StringValue("DsssRate1Mbps"));
    Config::SetDefault("ns3::WifiMacQueue::MaxSize", StringValue("1000p"));

    NodeContainer nodes;
    nodes.Create(g.hops + 1);
    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue("DsssRate2Mbps"),
                                 "ControlMode",
                                 StringValue("DsssRate1Mbps"));
    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    if (g.positioned)
    {
        channel.AddPropagationLoss("ns3::RangePropagationLossModel",
                                   "MaxRange",
                                   DoubleValue(115.0));
    }
    else
    {
        channel.AddPropagationLoss("ns3::FixedRssLossModel", "Rss", DoubleValue(-80.0));
    }
    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, nodes);

    MobilityHelper mobility;
    Ptr<ListPositionAllocator> positions = CreateObject<ListPositionAllocator>();
    for (uint32_t index = 0; index <= g.hops; ++index)
    {
        positions->Add(Vector(index * 100.0, 0.0, 0.0));
    }
    mobility.SetPositionAllocator(positions);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(nodes);

    InternetStackHelper internet;
    internet.Install(nodes);
    Ipv4AddressHelper ip;
    ip.SetBase("10.18.0.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = ip.Assign(devices);

    TypeId udp = TypeId::LookupByName("ns3::UdpSocketFactory");
    std::vector<Ptr<Socket>> dataRx;
    std::vector<Ptr<Socket>> controlRx;
    for (uint32_t index = 0; index <= g.hops; ++index)
    {
        Ptr<Socket> data = Socket::CreateSocket(nodes.Get(index), udp);
        data->Bind(InetSocketAddress(Ipv4Address::GetAny(), 9000));
        data->SetRecvCallback(MakeCallback(&ReceiveData));
        dataRx.push_back(data);
        Ptr<Socket> control = Socket::CreateSocket(nodes.Get(index), udp);
        control->Bind(InetSocketAddress(Ipv4Address::GetAny(), 9001));
        control->SetRecvCallback(MakeCallback(&DrainControl));
        controlRx.push_back(control);
    }
    for (uint32_t hop = 0; hop < g.hops; ++hop)
    {
        Ptr<Socket> data = Socket::CreateSocket(nodes.Get(hop), udp);
        data->Connect(InetSocketAddress(interfaces.GetAddress(hop + 1), 9000));
        g.dataTx.push_back(data);
        Ptr<Socket> control = Socket::CreateSocket(nodes.Get(hop), udp);
        control->Connect(InetSocketAddress(interfaces.GetAddress(hop + 1), 9001));
        g.controlTx.push_back(control);
    }

    for (uint32_t index = 0; index < devices.GetN(); ++index)
    {
        Ptr<WifiNetDevice> device = DynamicCast<WifiNetDevice>(devices.Get(index));
        device->GetMac()->TraceConnectWithoutContext("MacTx", MakeCallback(&MacTx));
        device->GetMac()->TraceConnectWithoutContext("MacTxDrop", MakeCallback(&MacTxDrop));
        device->GetPhy()->TraceConnectWithoutContext("PhyTxBegin", MakeCallback(&PhyTxBegin));
        device->GetPhy()->TraceConnectWithoutContext("PhyRxEnd", MakeCallback(&PhyRxEnd));
        device->GetPhy()->TraceConnectWithoutContext("PhyRxDrop", MakeCallback(&PhyRxDrop));
    }

    Ptr<UniformRandomVariable> uniform = CreateObject<UniformRandomVariable>();
    uniform->SetStream(g.seed);
    double arrival = 1.0;
    const double interval = g.load == "high" ? 0.001 : (g.load == "medium" ? 0.01 : 0.08);
    for (uint32_t seq = 0; seq < g.packets; ++seq)
    {
        if (seq > 0)
        {
            arrival += g.traffic == "poisson" ? uniform->GetValue(0.2, 1.8) * interval : interval;
        }
        g.createdAt[seq] = arrival;
        Simulator::Schedule(Seconds(arrival), &Trace, seq, 0, "APP_CREATE", g.traffic);
        if (g.causal)
        {
            Simulator::Schedule(Seconds(arrival), &SendHop, seq, 0);
        }
        else
        {
            for (uint32_t hop = 0; hop < g.hops; ++hop)
            {
                const uint64_t spacingUs = g.protocol == "fixed" ? 650 : 120;
                Simulator::Schedule(Seconds(arrival) + MicroSeconds(hop * spacingUs),
                                    &SendHop,
                                    seq,
                                    hop);
            }
        }
    }

    Simulator::Stop(Seconds(arrival + 15.0));
    Simulator::Run();
    Simulator::Destroy();
    g.trace.close();

    const std::vector<std::string> terminals = {
        "DELIVERED",
        "APP_SEND_REJECTED",
        "SOCKET_BUFFER_DROP",
        "MAC_QUEUE_DROP",
        "MAC_RETRY_EXHAUSTED",
        "PHY_RX_DROP",
        "PROTOCOL_CONTROL_TIMEOUT",
        "PROTOCOL_RETRY_EXHAUSTED",
        "SIMULATION_STOP_TIMEOUT",
        "DUPLICATE_SUPPRESSED",
        "UNKNOWN_LOSS",
    };
    std::map<std::string, uint32_t> terminalCounts;
    for (const auto& terminal : terminals)
    {
        terminalCounts[terminal] = 0;
    }
    std::vector<std::string> packetTerminal(g.packets);
    for (uint32_t seq = 0; seq < g.packets; ++seq)
    {
        const auto& state = g.packetState[seq];
        std::string terminal;
        if (state.delivered)
        {
            terminal = "DELIVERED";
        }
        else if (state.appRejected)
        {
            terminal = "APP_SEND_REJECTED";
        }
        else if (state.macDrop)
        {
            terminal = "MAC_QUEUE_DROP";
        }
        else if (state.phyDrop)
        {
            terminal = "PHY_RX_DROP";
        }
        else
        {
            terminal = "SIMULATION_STOP_TIMEOUT";
        }
        packetTerminal[seq] = terminal;
        terminalCounts[terminal]++;
    }

    std::ofstream output(outputPath);
    if (!output)
    {
        NS_FATAL_ERROR("cannot open output");
    }
    output << std::boolalpha << std::setprecision(15)
           << "{\n"
           << "  \"platform\": \"ns3-3.43-adhoc-wifi-udp-diagnostic\",\n"
           << "  \"purpose\": \"root-cause diagnosis only; not performance re-judgment\",\n"
           << "  \"mode\": \"" << g.mode << "\",\n"
           << "  \"protocol\": \"" << g.protocol << "\",\n"
           << "  \"hops\": " << g.hops << ",\n"
           << "  \"packets\": " << g.packets << ",\n"
           << "  \"load\": \"" << g.load << "\",\n"
           << "  \"traffic\": \"" << g.traffic << "\",\n"
           << "  \"seed\": " << g.seed << ",\n"
           << "  \"causal_forwarding\": " << g.causal << ",\n"
           << "  \"positioned_chain\": " << g.positioned << ",\n"
           << "  \"k2_segment\": " << g.k2 << ",\n"
           << "  \"reservation_window\": " << g.reservationWindow << ",\n"
           << "  \"created\": " << g.packets << ",\n"
           << "  \"delivered\": " << terminalCounts["DELIVERED"] << ",\n"
           << "  \"delivery_ratio\": "
           << static_cast<double>(terminalCounts["DELIVERED"]) / g.packets << ",\n"
           << "  \"unknown_loss\": " << terminalCounts["UNKNOWN_LOSS"] << ",\n"
           << "  \"boundary_counters\": {\"mac_enqueue\": " << g.macEnqueue
           << ", \"mac_drop\": " << g.macDrop << ", \"phy_tx\": " << g.phyTx
           << ", \"phy_rx\": " << g.phyRx << ", \"phy_drop\": " << g.phyDrop << "},\n"
           << "  \"terminal_counts\": {\n";
    for (size_t index = 0; index < terminals.size(); ++index)
    {
        output << "    \"" << terminals[index] << "\": " << terminalCounts[terminals[index]]
               << (index + 1 == terminals.size() ? "\n" : ",\n");
    }
    output << "  },\n"
           << "  \"frozen_parameters\": {\"K\": " << K << ", \"CWmin\": " << CW_MIN
           << ", \"CWmax\": " << CW_MAX << ", \"retry_limit\": " << RETRY_LIMIT
           << ", \"payload_bytes\": " << PAYLOAD_BYTES << ", \"data_rate_mbps\": "
           << DATA_RATE_MBPS << ", \"control_rate_mbps\": " << CONTROL_RATE_MBPS
           << ", \"slot_us\": " << SLOT_US << "},\n"
           << "  \"packets_detail\": [\n";
    for (uint32_t seq = 0; seq < g.packets; ++seq)
    {
        const auto& state = g.packetState[seq];
        output << "    {\"seq\": " << seq << ", \"terminal\": \"" << packetTerminal[seq]
               << "\", \"terminal_hop\": " << state.terminalHop
               << ", \"reservation_segments\": " << state.reservationSegments
               << ", \"max_segment_hops\": " << state.maxSegmentHops << "}"
               << (seq + 1 == g.packets ? "\n" : ",\n");
    }
    output << "  ]\n}\n";
    return 0;
}
