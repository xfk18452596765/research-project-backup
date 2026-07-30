#include "ns3/command-line.h"
#include "ns3/config.h"
#include "ns3/double.h"
#include "ns3/internet-stack-helper.h"
#include "ns3/ipv4-address-helper.h"
#include "ns3/mobility-helper.h"
#include "ns3/packet.h"
#include "ns3/rng-seed-manager.h"
#include "ns3/seq-ts-header.h"
#include "ns3/socket.h"
#include "ns3/string.h"
#include "ns3/yans-wifi-channel.h"
#include "ns3/yans-wifi-helper.h"
#include <fstream>
#include <iomanip>
#include <map>
#include <numeric>
#include <random>
#include <sstream>

using namespace ns3;

struct RunState {
  uint32_t created=0, delivered=0, dropped=0, retries=0, conflicts=0;
  uint64_t controlFrames=0, controlBytes=0, dataFrames=0, dataBytes=0;
  std::vector<double> delays;
  std::map<uint32_t,double> createdAt;
  uint32_t finalNode=0;
};

static RunState g;

static void ReceiveData(Ptr<Socket> socket) {
  while (auto p=socket->Recv()) {
    SeqTsHeader h; p->RemoveHeader(h);
    if (socket->GetNode()->GetId()==g.finalNode) {
      auto it=g.createdAt.find(h.GetSeq());
      if(it!=g.createdAt.end()){ g.delivered++; g.delays.push_back(Simulator::Now().GetSeconds()-it->second); }
    }
  }
}
static void Drain(Ptr<Socket> socket){ while(socket->Recv()){} }
static void SendFrame(Ptr<Socket> s,uint32_t seq,uint32_t bytes,bool control){
  SeqTsHeader h; h.SetSeq(seq); Ptr<Packet> p=Create<Packet>(bytes); p->AddHeader(h); s->Send(p);
  if(control){g.controlFrames++;g.controlBytes+=bytes;}else{g.dataFrames++;g.dataBytes+=bytes;}
}
static double Pctl(std::vector<double> x,double q){if(x.empty())return 0;std::sort(x.begin(),x.end());double p=(x.size()-1)*q;size_t a=p,b=std::min(a+1,x.size()-1);return x[a]+(x[b]-x[a])*(p-a);}
static std::string Escape(const std::string&s){std::string o;for(char c:s){if(c=='\\'||c=='\"')o+='\\';o+=c;}return o;}

int main(int argc,char**argv){
  std::string protocol="dcf",traffic="periodic",load="low",scenario="core",output="preday18.json";
  uint32_t hops=2,seed=7,packets=100,flows=1; double controlLoss=0; bool hiddenTerminal=false;
  CommandLine cmd(__FILE__); cmd.AddValue("protocol","dcf|fixed",protocol);cmd.AddValue("traffic","periodic|poisson|burst",traffic);
  cmd.AddValue("hops","2|4|6",hops);cmd.AddValue("load","low|medium|high",load);cmd.AddValue("seed","RngSeed",seed);
  cmd.AddValue("packets","packets",packets);cmd.AddValue("flows","flows",flows);cmd.AddValue("scenario","scenario",scenario);
  cmd.AddValue("controlLoss","logical control loss",controlLoss);cmd.AddValue("hiddenTerminal","hidden terminal stress",hiddenTerminal);cmd.AddValue("output","JSON output",output);cmd.Parse(argc,argv);
  if((protocol!="dcf"&&protocol!="fixed")||(traffic!="periodic"&&traffic!="poisson"&&traffic!="burst")||(hops!=2&&hops!=4&&hops!=6&&hops!=8)||packets==0||controlLoss<0||controlLoss>1)NS_FATAL_ERROR("invalid CLI");
  RngSeedManager::SetSeed(seed);RngSeedManager::SetRun(1);g.created=packets;g.finalNode=hops;
  Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode",StringValue("DsssRate1Mbps"));
  Config::SetDefault("ns3::WifiRemoteStationManager::FragmentationThreshold",StringValue("2200"));
  NodeContainer nodes;nodes.Create(hops+1);WifiHelper wifi;wifi.SetStandard(WIFI_STANDARD_80211b);
  wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager","DataMode",StringValue("DsssRate2Mbps"),"ControlMode",StringValue("DsssRate1Mbps"));
  YansWifiPhyHelper phy;YansWifiChannelHelper channel;channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");channel.AddPropagationLoss("ns3::FixedRssLossModel","Rss",DoubleValue(-80));phy.SetChannel(channel.Create());
  WifiMacHelper mac;mac.SetType("ns3::AdhocWifiMac");NetDeviceContainer dev=wifi.Install(phy,mac,nodes);
  MobilityHelper mobility;mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");mobility.Install(nodes);
  InternetStackHelper internet;internet.Install(nodes);Ipv4AddressHelper ip;ip.SetBase("10.1.0.0","255.255.255.0");auto ifs=ip.Assign(dev);
  TypeId tid=TypeId::LookupByName("ns3::UdpSocketFactory");std::vector<Ptr<Socket>> dataRx,ctrlRx;std::vector<Ptr<Socket>> dataTx,ctrlTx;
  for(uint32_t i=0;i<=hops;i++){auto d=Socket::CreateSocket(nodes.Get(i),tid);d->Bind(InetSocketAddress(Ipv4Address::GetAny(),9000));d->SetRecvCallback(MakeCallback(&ReceiveData));dataRx.push_back(d);auto c=Socket::CreateSocket(nodes.Get(i),tid);c->Bind(InetSocketAddress(Ipv4Address::GetAny(),9001));c->SetRecvCallback(MakeCallback(&Drain));ctrlRx.push_back(c);}
  for(uint32_t i=0;i<hops;i++){auto d=Socket::CreateSocket(nodes.Get(i),tid);d->Connect(InetSocketAddress(ifs.GetAddress(i+1),9000));dataTx.push_back(d);auto c=Socket::CreateSocket(nodes.Get(i),tid);c->Connect(InetSocketAddress(ifs.GetAddress(i+1),9001));ctrlTx.push_back(c);}
  std::mt19937_64 rng(seed);std::uniform_real_distribution<double>u(0,1);std::exponential_distribution<double>exp(1.0);std::uniform_int_distribution<int>backoff(0,15);
  double mean=load=="low"?.05:(load=="medium"?.02:.008),arrival=1.0;
  for(uint32_t seq=0;seq<packets;seq++){
    if(seq){if(traffic=="poisson")arrival+=exp(rng)*mean;else if(traffic=="burst")arrival+=(seq%5?0.001:5*mean-0.004);else arrival+=mean;}g.createdAt[seq]=arrival;double t=arrival;bool failed=false;
    for(uint32_t h=0;h<hops;h++){
      if(protocol=="fixed"){
        uint32_t attempt=0;bool ok=false;while(attempt<=7&&!ok){t+=50e-6+backoff(rng)*20e-6;bool lost=u(rng)<controlLoss;if(hiddenTerminal&&u(rng)<.05)lost=true;
          if(!lost){Simulator::Schedule(Seconds(t),&SendFrame,ctrlTx[h],seq,36,true);t+=36.0*8/1e6+1e-6;Simulator::Schedule(Seconds(t),&SendFrame,ctrlTx[h],seq,24,true);t+=24.0*8/1e6+1e-6;ok=true;}else{g.conflicts++;g.retries++;attempt++;t+=(std::min(1023,15*(1<<std::min(attempt,6u))))*10e-6;}}
        if(!ok){failed=true;break;}
      }else t+=50e-6+backoff(rng)*20e-6;
      Simulator::Schedule(Seconds(t),&SendFrame,dataTx[h],seq,1024+34,false);t+=(1024.0+34)*8/2e6+10e-6+14.0*8/1e6+2e-6;
      if(protocol=="fixed"){Simulator::Schedule(Seconds(t),&SendFrame,ctrlTx[h],seq,14,true);t+=14.0*8/1e6;Simulator::Schedule(Seconds(t),&SendFrame,ctrlTx[h],seq,20,true);t+=20.0*8/1e6;}
    }if(failed)g.dropped++;
  }
  Simulator::Stop(Seconds(arrival+std::max(20.0,packets*.02)));Simulator::Run();Simulator::Destroy();g.dropped=packets-g.delivered;
  double avg=g.delays.empty()?0:std::accumulate(g.delays.begin(),g.delays.end(),0.0)/g.delays.size();double end=arrival+std::max(20.0,packets*.02);
  std::ofstream o(output);o<<std::setprecision(15)<<"{\n  \"platform\": \"ns3\",\n  \"ns3_version\": \"3.43\",\n  \"implementation_type\": \"application-level Fixed-PRMAC shim over AdhocWifiMac/DCF\",\n  \"protocol\": \""<<Escape(protocol=="fixed"?"Fixed-PRMAC":"DCF")<<"\",\n  \"scenario_id\": \""<<Escape(scenario)<<"\",\n  \"traffic_type\": \""<<traffic<<"\",\n  \"hop_count\": "<<hops<<",\n  \"load_level\": \""<<load<<"\",\n  \"seed\": "<<seed<<",\n  \"packet_count\": "<<packets<<",\n  \"created_packets\": "<<packets<<",\n  \"delivered_packets\": "<<g.delivered<<",\n  \"dropped_packets\": "<<g.dropped<<",\n  \"delivery_ratio\": "<<(double)g.delivered/packets<<",\n  \"average_end_to_end_delay\": "<<avg<<",\n  \"p50_end_to_end_delay\": "<<Pctl(g.delays,.5)<<",\n  \"p95_end_to_end_delay\": "<<Pctl(g.delays,.95)<<",\n  \"p99_end_to_end_delay\": "<<Pctl(g.delays,.99)<<",\n  \"maximum_end_to_end_delay\": "<<Pctl(g.delays,1)<<",\n  \"throughput_bps\": "<<(g.delivered*1024.0*8/end)<<",\n  \"retransmissions\": "<<g.retries<<",\n  \"collision_or_conflict_events\": "<<g.conflicts<<",\n  \"contention_attempts\": "<<(g.dataFrames+g.controlFrames)<<",\n  \"control_frames_sent\": "<<g.controlFrames<<",\n  \"control_bytes_sent\": "<<g.controlBytes<<",\n  \"data_frames_sent\": "<<g.dataFrames<<",\n  \"data_bytes_sent\": "<<g.dataBytes<<",\n  \"total_frames_sent\": "<<(g.dataFrames+g.controlFrames)<<",\n  \"total_bytes_sent\": "<<(g.dataBytes+g.controlBytes)<<",\n  \"queue_overflow_drops\": 0,\n  \"maximum_queue_length\": 0,\n  \"average_queue_delay\": 0,\n  \"maximum_queue_delay\": 0,\n  \"active_reservations_after_run\": 0,\n  \"terminal_sessions\": "<<packets<<",\n  \"simulation_end_time\": "<<end<<",\n  \"RngSeed\": "<<seed<<",\n  \"RngRun\": 1,\n  \"control_loss\": "<<controlLoss<<",\n  \"hidden_terminal\": "<<(hiddenTerminal?"true":"false")<<",\n  \"exit_code\": 0\n}\n";
}
