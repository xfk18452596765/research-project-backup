/* Independent V2 smoke executable.  It deliberately uses ns-3 DCF, not a
 * synthetic scheduler.  Fixed-PRMAC requires a separately audited Wi-Fi MAC
 * access-path extension before it may be selected as a passing protocol. */
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/wifi-module.h"
using namespace ns3;
NS_LOG_COMPONENT_DEFINE ("PreDay18SemanticBaselineV2");
int main (int argc, char* argv[])
{
  uint32_t hops = 2, packets = 10; double spacing = 80.0;
  CommandLine cmd (__FILE__); cmd.AddValue ("hops", "chain hop count", hops);
  cmd.AddValue ("packets", "packet count", packets); cmd.Parse (argc, argv);
  NodeContainer nodes; nodes.Create (hops + 1);
  YansWifiChannelHelper channel = YansWifiChannelHelper::Default ();
  YansWifiPhyHelper phy; phy.SetChannel (channel.Create ());
  WifiHelper wifi; wifi.SetStandard (WIFI_STANDARD_80211b);
  wifi.SetRemoteStationManager ("ns3::ConstantRateWifiManager", "DataMode", StringValue ("DsssRate2Mbps"), "ControlMode", StringValue ("DsssRate1Mbps"));
  WifiMacHelper mac; mac.SetType ("ns3::AdhocWifiMac"); NetDeviceContainer devs = wifi.Install (phy, mac, nodes);
  MobilityHelper mobility; Ptr<ListPositionAllocator> pos = CreateObject<ListPositionAllocator> ();
  for (uint32_t i=0; i<=hops; ++i) pos->Add (Vector (i * spacing, 0, 0));
  mobility.SetPositionAllocator (pos); mobility.SetMobilityModel ("ns3::ConstantPositionMobilityModel"); mobility.Install (nodes);
  InternetStackHelper stack; stack.Install (nodes); Ipv4AddressHelper address; address.SetBase ("10.1.0.0", "255.255.255.0"); auto ifaces = address.Assign (devs);
  uint16_t port=9000; PacketSinkHelper sink ("ns3::UdpSocketFactory", InetSocketAddress (ifaces.GetAddress(hops),port)); sink.Install(nodes.Get(hops)).Start(Seconds(0));
  OnOffHelper app ("ns3::UdpSocketFactory", InetSocketAddress(ifaces.GetAddress(hops),port)); app.SetAttribute("PacketSize",UintegerValue(1024)); app.SetAttribute("DataRate",DataRateValue(DataRate("1Mbps"))); app.SetAttribute("MaxBytes",UintegerValue(packets*1024)); app.Install(nodes.Get(0)).Start(Seconds(1));
  Simulator::Stop (Seconds (5)); Simulator::Run (); Simulator::Destroy (); return 0;
}
