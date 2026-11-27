/*
 * Plano de Dados — Abordagem híbrida Dijkstra (ingestão) + Kruskal (difusão)
 * NS-3.44
 *
 * Lê topologia_ns3.json (gerado por gerar_topologia.py) e executa UMA das
 * fases, conforme os argumentos:
 *
 *  FASE 1 — Ingestão (unicast UDP, nós de borda 6..11 -> Sink 0)
 *    --fase=ingestao --rota=dijkstra         rotas estáticas = caminhos de Dijkstra do JSON
 *    --fase=ingestao --rota=saltos           rotas estáticas = menor nº de saltos (linha de base)
 *    --fase=ingestao --rota=global_latencia  roteamento global do NS-3 com métrica = atraso
 *                                            (validação: o Dijkstra interno do NS-3 deve
 *                                             produzir as mesmas rotas do Python)
 *
 *  FASE 2 — Difusão (Sink 0 -> todos os nós; cada nó repassa a mensagem)
 *    --fase=difusao --modo=mst        repassa só aos filhos na MST (Kruskal)
 *    --fase=difusao --modo=spt        repassa só aos filhos na SPT (Dijkstra)
 *    --fase=difusao --modo=flood      inundação: repassa a todos os vizinhos, exceto
 *                                     quem enviou, apenas na 1ª cópia (supressão de duplicatas)
 *    --fase=difusao --modo=flood_ttl  inundação pura com TTL (sem supressão de duplicatas):
 *                                     ilustra a tempestade de difusão
 *
 * Saídas (prefixo = --saida, padrão "resultados/<fase>_<modo|rota>"):
 *    <prefixo>_flowmon.xml   FlowMonitor
 *    <prefixo>_fluxos.csv    (ingestão) métricas por fluxo + rota e custo teórico
 *    <prefixo>_nos.csv       (difusão)  métricas por nó receptor
 *    <prefixo>_resumo.csv    (difusão)  totais de transmissões, duplicatas, cobertura
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"

#include <nlohmann/json.hpp>

#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <vector>

using namespace ns3;
using json = nlohmann::json;

NS_LOG_COMPONENT_DEFINE("SimulacaoHibridaTCC");

// ---------------------------------------------------------------------------
// Estado global da topologia
// ---------------------------------------------------------------------------
static std::map<std::pair<uint32_t, uint32_t>, Ipv4Address> g_addr; // (u,v) -> IP de v no enlace u-v
static std::map<std::pair<uint32_t, uint32_t>, uint32_t> g_if;      // (u,v) -> interface de u para v
static std::map<uint32_t, std::vector<uint32_t>> g_vizinhos;
static std::map<Ipv4Address, uint32_t> g_ipParaNo;

// ---------------------------------------------------------------------------
// Estatísticas da difusão
// ---------------------------------------------------------------------------
struct EstatNo
{
    uint64_t rxTotal = 0;     // cópias recebidas (inclui duplicatas)
    uint64_t rxUnicas = 0;    // mensagens distintas recebidas
    uint64_t tx = 0;          // transmissões feitas por este nó
    double somaAtrasoMs = 0;  // atraso da 1ª cópia de cada mensagem
    double somaSaltos = 0;    // saltos percorridos pela 1ª cópia
};
static std::map<uint32_t, EstatNo> g_est;

// ---------------------------------------------------------------------------
// Aplicação de difusão (encaminhamento na camada de aplicação, salto a salto)
// Cabeçalho no início do payload:
//   seq (4 B) | instante de envio na origem em ns (8 B) | TTL (1 B) |
//   saltos (1 B) | id do remetente (2 B)
// ---------------------------------------------------------------------------
class DifusaoApp : public Application
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid = TypeId("DifusaoApp").SetParent<Application>().AddConstructor<DifusaoApp>();
        return tid;
    }

    void Configurar(uint32_t id, std::string modo, std::vector<uint32_t> filhos, bool ehSink,
                    uint32_t numMsgs, Time intervalo, uint32_t tamanho, uint8_t ttl, uint16_t porta)
    {
        m_id = id;
        m_modo = modo;
        m_filhos = filhos;
        m_ehSink = ehSink;
        m_numMsgs = numMsgs;
        m_intervalo = intervalo;
        m_tamanho = tamanho;
        m_ttl = ttl;
        m_porta = porta;
    }

  private:
    static const uint32_t HDR = 16;

    void StartApplication() override
    {
        m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_porta));
        m_socket->SetRecvCallback(MakeCallback(&DifusaoApp::Receber, this));
        if (m_ehSink)
        {
            m_evento = Simulator::ScheduleNow(&DifusaoApp::GerarMensagem, this);
        }
    }

    void StopApplication() override
    {
        Simulator::Cancel(m_evento);
        if (m_socket)
        {
            m_socket->SetRecvCallback(MakeNullCallback<void, Ptr<Socket>>());
            m_socket->Close();
        }
    }

    // Destinos do repasse conforme o modo
    std::vector<uint32_t> Destinos(int32_t remetente) const
    {
        if (m_modo == "mst" || m_modo == "spt")
        {
            return m_filhos; // árvore: só os filhos
        }
        std::vector<uint32_t> d; // flood / flood_ttl: todos os vizinhos menos o remetente
        for (uint32_t v : g_vizinhos.at(m_id))
        {
            if (static_cast<int32_t>(v) != remetente)
            {
                d.push_back(v);
            }
        }
        return d;
    }

    void Enviar(uint32_t seq, uint64_t t0, uint8_t ttl, uint8_t saltos, int32_t remetente)
    {
        for (uint32_t v : Destinos(remetente))
        {
            std::vector<uint8_t> buf(m_tamanho, 0);
            std::memcpy(&buf[0], &seq, 4);
            std::memcpy(&buf[4], &t0, 8);
            buf[12] = ttl;
            buf[13] = saltos;
            uint16_t eu = static_cast<uint16_t>(m_id);
            std::memcpy(&buf[14], &eu, 2);
            Ptr<Packet> p = Create<Packet>(buf.data(), m_tamanho);
            m_socket->SendTo(p, 0, InetSocketAddress(g_addr.at({m_id, v}), m_porta));
            g_est[m_id].tx++;
        }
    }

    void GerarMensagem()
    {
        uint64_t t0 = Simulator::Now().GetNanoSeconds();
        Enviar(m_seq, t0, m_ttl, 0, -1);
        m_seq++;
        if (m_seq < m_numMsgs)
        {
            m_evento = Simulator::Schedule(m_intervalo, &DifusaoApp::GerarMensagem, this);
        }
    }

    void Receber(Ptr<Socket> s)
    {
        Ptr<Packet> p;
        Address de;
        while ((p = s->RecvFrom(de)))
        {
            uint8_t hdr[HDR];
            p->CopyData(hdr, HDR);
            uint32_t seq;
            uint64_t t0;
            uint16_t rem;
            std::memcpy(&seq, &hdr[0], 4);
            std::memcpy(&t0, &hdr[4], 8);
            uint8_t ttl = hdr[12];
            uint8_t saltos = hdr[13] + 1;
            std::memcpy(&rem, &hdr[14], 2);

            if (m_ehSink)
            {
                g_est[m_id].rxTotal++; // cópias que voltaram ao Sink (só no flooding)
                continue;
            }
            EstatNo& e = g_est[m_id];
            e.rxTotal++;
            bool primeira = m_vistos.insert(seq).second;
            if (primeira)
            {
                e.rxUnicas++;
                e.somaAtrasoMs += (Simulator::Now().GetNanoSeconds() - t0) / 1e6;
                e.somaSaltos += saltos;
            }

            if (m_modo == "flood_ttl")
            {
                if (ttl > 1)
                {
                    Enviar(seq, t0, ttl - 1, saltos, rem); // sem supressão: tempestade
                }
            }
            else if (primeira)
            {
                Enviar(seq, t0, ttl, saltos, rem); // árvore ou flood com supressão
            }
        }
    }

    Ptr<Socket> m_socket;
    EventId m_evento;
    uint32_t m_id = 0, m_numMsgs = 0, m_tamanho = 512, m_seq = 0;
    uint16_t m_porta = 9100;
    uint8_t m_ttl = 4;
    bool m_ehSink = false;
    std::string m_modo;
    std::vector<uint32_t> m_filhos;
    Time m_intervalo;
    std::set<uint32_t> m_vistos;
};

// ---------------------------------------------------------------------------
static std::string CaminhoStr(const json& c)
{
    std::ostringstream os;
    for (size_t i = 0; i < c.size(); ++i)
    {
        os << (i ? "-" : "") << c[i].get<int>();
    }
    return os.str();
}

int
main(int argc, char* argv[])
{
    std::string jsonPath = "topologia_ns3.json";
    std::string fase = "ingestao";
    std::string rota = "dijkstra";
    std::string modo = "mst";
    std::string saida = "";
    double taxaMbps = 5.0;   // taxa de aplicação por nó de borda (Fase 1)
    uint32_t pacote = 1024;  // bytes de carga útil (Fase 1)
    uint32_t pacoteDif = 512;
    double intervaloDifMs = 20.0;
    uint32_t ttl = 4;
    uint32_t semente = 1;

    CommandLine cmd(__FILE__);
    cmd.AddValue("json", "Arquivo JSON da topologia", jsonPath);
    cmd.AddValue("fase", "ingestao | difusao", fase);
    cmd.AddValue("rota", "Fase 1: dijkstra | saltos | global_latencia", rota);
    cmd.AddValue("modo", "Fase 2: mst | spt | flood | flood_ttl", modo);
    cmd.AddValue("saida", "Prefixo dos arquivos de saída", saida);
    cmd.AddValue("taxaMbps", "Fase 1: taxa por nó de borda (Mbps)", taxaMbps);
    cmd.AddValue("pacote", "Fase 1: carga útil (bytes)", pacote);
    cmd.AddValue("pacoteDif", "Fase 2: carga útil (bytes)", pacoteDif);
    cmd.AddValue("intervaloDifMs", "Fase 2: intervalo entre mensagens (ms)", intervaloDifMs);
    cmd.AddValue("ttl", "Fase 2 (flood_ttl): TTL inicial", ttl);
    cmd.AddValue("semente", "Semente do gerador aleatório", semente);
    cmd.Parse(argc, argv);
    RngSeedManager::SetSeed(semente);

    if (saida.empty())
    {
        saida = "resultados/" + fase + "_" + (fase == "ingestao" ? rota : modo);
    }

    std::ifstream f(jsonPath);
    if (!f.is_open())
    {
        std::cerr << "Erro: não foi possível abrir " << jsonPath << std::endl;
        return 1;
    }
    json J;
    f >> J;

    const uint32_t N = J["num_nodes"];
    const uint32_t SINK = J["sink_node"];

    // -----------------------------------------------------------------------
    // Topologia física (TODOS os enlaces do JSON, com banda e atraso próprios)
    // -----------------------------------------------------------------------
    NodeContainer nos;
    nos.Create(N);
    InternetStackHelper internet;
    internet.Install(nos);

    Ipv4AddressHelper ipv4;
    uint32_t sub = 1;
    for (const auto& l : J["links"])
    {
        uint32_t u = l["src"], v = l["dst"];
        uint32_t bw = l["bw_mbps"], d = l["delay_ms"];
        PointToPointHelper p2p;
        p2p.SetDeviceAttribute("DataRate", StringValue(std::to_string(bw) + "Mbps"));
        p2p.SetChannelAttribute("Delay", StringValue(std::to_string(d) + "ms"));
        NetDeviceContainer dev = p2p.Install(nos.Get(u), nos.Get(v));

        std::string base = "10.1." + std::to_string(sub++) + ".0";
        ipv4.SetBase(base.c_str(), "255.255.255.0");
        Ipv4InterfaceContainer ifc = ipv4.Assign(dev);

        g_addr[{u, v}] = ifc.GetAddress(1); // endereço de v visto por u
        g_addr[{v, u}] = ifc.GetAddress(0);
        g_ipParaNo[ifc.GetAddress(0)] = u;
        g_ipParaNo[ifc.GetAddress(1)] = v;
        Ptr<Ipv4> ipU = nos.Get(u)->GetObject<Ipv4>();
        Ptr<Ipv4> ipV = nos.Get(v)->GetObject<Ipv4>();
        g_if[{u, v}] = ipU->GetInterfaceForDevice(dev.Get(0));
        g_if[{v, u}] = ipV->GetInterfaceForDevice(dev.Get(1));
        g_vizinhos[u].push_back(v);
        g_vizinhos[v].push_back(u);

        // métrica OSPF-like = atraso (só usada por --rota=global_latencia)
        ipU->SetMetric(g_if[{u, v}], d);
        ipV->SetMetric(g_if[{v, u}], d);
    }
    for (auto& [n, viz] : g_vizinhos)
    {
        std::sort(viz.begin(), viz.end());
    }

    std::cout << "Topologia: " << N << " nós, " << J["links"].size() << " enlaces, Sink = " << SINK
              << std::endl;

    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor;

    // =======================================================================
    // FASE 1 — INGESTÃO
    // =======================================================================
    if (fase == "ingestao")
    {
       // const Ipv4Address sinkIp = g_addr.at({1, SINK}); // um endereço do Sink
// Procura os vizinhos existentes do Sink.
const auto vizinhosSink = g_vizinhos.find(SINK);

// Confere se o Sink possui alguma conexão.
if (vizinhosSink == g_vizinhos.end() || vizinhosSink->second.empty())
{
    std::cerr << "Erro: Sink sem enlaces." << std::endl;
    return 1;
}

// Escolhe um vizinho real e obtém o endereço do Sink nesse enlace.
const uint32_t vizinhoSink = vizinhosSink->second.front();
const Ipv4Address sinkIp = g_addr.at({vizinhoSink, SINK});
        const uint16_t porta = 9000;
        std::map<uint32_t, json> rotas;

        if (rota == "dijkstra" || rota == "saltos")
        {
            const json& R = J["ingestion"][rota == "dijkstra" ? "dijkstra_paths" : "min_hops_paths"];
            Ipv4StaticRoutingHelper srh;
            std::map<uint32_t, uint32_t> proximo; // nó -> próximo salto instalado
            for (uint32_t s : J["edge_nodes"])
            {
                const json& c = R[std::to_string(s)];
                rotas[s] = c;
                for (size_t i = 0; i + 1 < c.size(); ++i)
                {
                    uint32_t a = c[i], b = c[i + 1];
                    if (proximo.count(a))
                    {
                        if (proximo[a] != b)
                        {
                            std::cerr << "Aviso: rotas inconsistentes no nó " << a << std::endl;
                        }
                        continue;
                    }
                    proximo[a] = b;
                    Ptr<Ipv4StaticRouting> sr = srh.GetStaticRouting(nos.Get(a)->GetObject<Ipv4>());
                    sr->AddHostRouteTo(sinkIp, g_addr.at({a, b}), g_if.at({a, b}));
                }
            }
            std::cout << "Rotas estáticas instaladas (" << rota << "):" << std::endl;
            for (auto& [s, c] : rotas)
            {
                std::cout << "  nó " << s << ": " << CaminhoStr(c) << std::endl;
            }
        }
        else if (rota == "global_latencia")
        {
            Ipv4GlobalRoutingHelper::PopulateRoutingTables(); // SPF interno do NS-3, métrica = atraso
            for (uint32_t s : J["edge_nodes"])
            {
                // reconstrói o caminho consultando as tabelas de roteamento
                json c = json::array({s});
                uint32_t atual = s;
                for (int k = 0; k < 20 && atual != SINK; ++k)
                {
                    Ptr<Ipv4> ip = nos.Get(atual)->GetObject<Ipv4>();
                    Ipv4Header h;
                    h.SetDestination(sinkIp);
                    Socket::SocketErrno err;
                    Ptr<Ipv4Route> r = ip->GetRoutingProtocol()->RouteOutput(nullptr, h, nullptr, err);
                    if (!r)
                    {
                        break;
                    }
                    Ipv4Address gw = r->GetGateway();
                    atual = (gw == Ipv4Address::GetZero()) ? SINK : g_ipParaNo.at(gw);
                    c.push_back(atual);
                }
                rotas[s] = c;
                std::cout << "  nó " << s << " (NS-3 global): " << CaminhoStr(c) << std::endl;
            }
        }
        else
        {
            std::cerr << "--rota inválida" << std::endl;
            return 1;
        }

        UdpServerHelper servidor(porta);
        ApplicationContainer appS = servidor.Install(nos.Get(SINK));
        appS.Start(Seconds(0.5));
        appS.Stop(Seconds(11.0));

        // intervalo = bits por pacote / taxa  (5 Mbps com 1024 B -> 1,6384 ms)
        Time intervalo = Seconds(pacote * 8.0 / (taxaMbps * 1e6));
        for (uint32_t s : J["edge_nodes"])
        {
            UdpClientHelper cli(sinkIp, porta);
            cli.SetAttribute("MaxPackets", UintegerValue(0)); // 0 = ilimitado
            cli.SetAttribute("Interval", TimeValue(intervalo));
            cli.SetAttribute("PacketSize", UintegerValue(pacote));
            ApplicationContainer a = cli.Install(nos.Get(s));
            a.Start(Seconds(1.0));
            a.Stop(Seconds(10.0));
        }

        monitor = flowmon.InstallAll();
        Simulator::Stop(Seconds(11.0));
        Simulator::Run();
        monitor->CheckForLostPackets();
        monitor->SerializeToXmlFile(saida + "_flowmon.xml", true, true);

        // ---- CSV por fluxo -------------------------------------------------
        auto cls = DynamicCast<Ipv4FlowClassifier>(flowmon.GetClassifier());
        std::ofstream csv(saida + "_fluxos.csv");
        csv << "no_origem,rota,saltos_rota,custo_teorico_ms,tx,rx,perda_pct,atraso_medio_ms,"
               "atraso_min_ms,atraso_max_ms,vazao_mbps,saltos_medidos\n";
        std::cout << "\nNó  Rota            Teórico  Medido(ms)  Vazão(Mbps)  Perda" << std::endl;
        for (auto& [id, st] : monitor->GetFlowStats())
        {
            auto t = cls->FindFlow(id);
            if (t.destinationPort != porta)
            {
                continue;
            }
            uint32_t s = g_ipParaNo.at(t.sourceAddress);
            const json& c = rotas[s];
            double custo = 0;
            for (size_t i = 0; i + 1 < c.size(); ++i)
            {
                for (const auto& l : J["links"])
                {
                    uint32_t a = c[i], b = c[i + 1];
                    if ((l["src"] == a && l["dst"] == b) || (l["src"] == b && l["dst"] == a))
                    {
                        custo += l["delay_ms"].get<double>();
                    }
                }
            }
            double dur = (st.timeLastRxPacket - st.timeFirstRxPacket).GetSeconds();
            double vazao = dur > 0 ? st.rxBytes * 8.0 / dur / 1e6 : 0;
            double atraso = st.rxPackets ? st.delaySum.GetSeconds() * 1e3 / st.rxPackets : 0;
            double perda = st.txPackets ? 100.0 * (st.txPackets - st.rxPackets) / st.txPackets : 0;
            double saltosMed = st.rxPackets ? 1.0 + double(st.timesForwarded) / st.rxPackets : 0;
            csv << s << "," << CaminhoStr(c) << "," << c.size() - 1 << "," << custo << ","
                << st.txPackets << "," << st.rxPackets << "," << perda << "," << atraso << ","
                << st.minDelay.GetSeconds() * 1e3 << "," << st.maxDelay.GetSeconds() * 1e3 << ","
                << vazao << "," << saltosMed << "\n";
            std::cout << std::setw(2) << s << "  " << std::left << std::setw(15) << CaminhoStr(c)
                      << std::right << std::setw(5) << custo << std::fixed << std::setprecision(2)
                      << std::setw(12) << atraso << std::setw(13) << vazao << std::setw(7) << perda
                      << "%" << std::endl;
        }
    }
    // =======================================================================
    // FASE 2 — DIFUSÃO
    // =======================================================================
    else if (fase == "difusao")
    {
        if (modo != "mst" && modo != "spt" && modo != "flood" && modo != "flood_ttl")
        {
            std::cerr << "--modo inválido" << std::endl;
            return 1;
        }
        const json* filhos = nullptr;
        if (modo == "mst" || modo == "spt")
        {
            filhos = &J["trees"][modo]["children"];
            std::cout << "Árvore de difusão (" << modo << "): ";
            for (const auto& e : J["trees"][modo]["edges"])
            {
                std::cout << "(" << e[0] << "," << e[1] << ") ";
            }
            std::cout << std::endl;
        }

        const double t0 = 11.0, t1 = 20.0;
        const uint32_t numMsgs = static_cast<uint32_t>((t1 - t0) * 1000.0 / intervaloDifMs);
        for (uint32_t n = 0; n < N; ++n)
        {
            std::vector<uint32_t> ch;
            if (filhos)
            {
                for (uint32_t c : (*filhos)[std::to_string(n)])
                {
                    ch.push_back(c);
                }
            }
            Ptr<DifusaoApp> app = CreateObject<DifusaoApp>();
            app->Configurar(n, modo, ch, n == SINK, numMsgs, MilliSeconds(intervaloDifMs), pacoteDif,
                            static_cast<uint8_t>(ttl), 9100);
            nos.Get(n)->AddApplication(app);
            app->SetStartTime(Seconds(n == SINK ? t0 : t0 - 0.5));
            app->SetStopTime(Seconds(t1 + 1.0));
            g_est[n]; // garante entrada
        }

        monitor = flowmon.InstallAll();
        Simulator::Stop(Seconds(t1 + 1.0));
        Simulator::Run();
        monitor->CheckForLostPackets();
        monitor->SerializeToXmlFile(saida + "_flowmon.xml", true, true);

        // Total de transmissões também pelo FlowMonitor (validação cruzada):
        // cada salto de difusão é um fluxo unicast entre vizinhos.
        uint64_t txFlow = 0, rxFlow = 0;
        for (auto& [id, st] : monitor->GetFlowStats())
        {
            txFlow += st.txPackets;
            rxFlow += st.rxPackets;
        }

        const json& dist = J["trees"][modo == "mst" ? "mst" : "spt"]["dist_from_sink_ms"];
        std::ofstream csv(saida + "_nos.csv");
        csv << "no,rx_total,rx_unicas,duplicatas,entrega_pct,tx,atraso_medio_ms,saltos_medios,"
               "dist_teorica_ms\n";
        uint64_t txTot = 0, rxTot = 0, uniTot = 0, cobertos = 0;
        for (uint32_t n = 0; n < N; ++n)
        {
            EstatNo& e = g_est[n];
            txTot += e.tx;
            if (n == SINK)
            {
                continue;
            }
            rxTot += e.rxTotal;
            uniTot += e.rxUnicas;
            if (e.rxUnicas == numMsgs)
            {
                cobertos++;
            }
            double atr = e.rxUnicas ? e.somaAtrasoMs / e.rxUnicas : 0;
            double sal = e.rxUnicas ? e.somaSaltos / e.rxUnicas : 0;
            csv << n << "," << e.rxTotal << "," << e.rxUnicas << "," << (e.rxTotal - e.rxUnicas) << ","
                << 100.0 * e.rxUnicas / numMsgs << "," << e.tx << "," << atr << "," << sal << ","
                << dist[std::to_string(n)].get<double>() << "\n";
        }
        uint64_t rxSink = g_est[SINK].rxTotal;
        std::ofstream res(saida + "_resumo.csv");
        res << "modo,mensagens,transmissoes_total,transmissoes_por_msg,copias_recebidas,"
               "duplicatas_total,duplicatas_por_msg,entrega_unica_pct,nos_cobertos,"
               "tx_flowmonitor,rx_flowmonitor,perdas_rede\n";
        double dup = double(rxTot + rxSink - uniTot);
        res << modo << "," << numMsgs << "," << txTot << "," << double(txTot) / numMsgs << ","
            << rxTot + rxSink << "," << dup << "," << dup / numMsgs << ","
            << 100.0 * uniTot / (double(numMsgs) * (N - 1)) << "," << cobertos << "/" << N - 1 << ","
            << txFlow << "," << rxFlow << "," << txFlow - rxFlow << "\n";

        std::cout << std::fixed << std::setprecision(2) << "Modo " << modo << ": " << numMsgs
                  << " mensagens, " << double(txTot) / numMsgs << " transmissões/msg, "
                  << dup / numMsgs << " duplicatas/msg, cobertura " << cobertos << "/" << N - 1
                  << ", perdas na rede " << txFlow - rxFlow << std::endl;
    }
    else
    {
        std::cerr << "--fase inválida" << std::endl;
        return 1;
    }

    Simulator::Destroy();
    std::cout << "Saídas: " << saida << "_*" << std::endl;
    return 0;
}
