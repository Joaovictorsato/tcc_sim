#!/usr/bin/env python3
"""
Confere os resultados da simulação contra os valores esperados pela teoria.
Executar depois de ./executar_todos.sh, dentro da pasta tcc_sim.

Cada verificação imprime OK ou FALHA. Se tudo estiver OK, os resultados
podem ir para o texto do TCC.
"""
import csv
import json
import os
import sys

R = "resultados"
J = json.load(open("topologia_ns3.json", encoding="utf-8"))
falhas = 0


def ler(nome):
    caminho = os.path.join(R, nome)
    if not os.path.exists(caminho):
        print(f"FALHA  arquivo ausente: {caminho}")
        sys.exit(1)
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def checa(cond, msg):
    global falhas
    print(("OK     " if cond else "FALHA  ") + msg)
    if not cond:
        falhas += 1


print("== Fase 1: ingestão")
dij = {int(l["no_origem"]): l for l in ler("ingestao_dijkstra_fluxos.csv")}
sal = {int(l["no_origem"]): l for l in ler("ingestao_saltos_fluxos.csv")}
glo = {int(l["no_origem"]): l for l in ler("ingestao_global_latencia_fluxos.csv")}

checa(len(dij) == 6, f"6 fluxos de ingestão (encontrados: {len(dij)})")
for n, l in sorted(dij.items()):
    esperado = "-".join(map(str, J["ingestion"]["dijkstra_paths"][str(n)]))
    checa(l["rota"] == esperado, f"nó {n}: rota Dijkstra {l['rota']} (esperado {esperado})")
    checa(glo[n]["rota"] == esperado, f"nó {n}: roteamento do NS-3 com métrica de atraso = Dijkstra do Python")
    perda = float(l["perda_pct"])
    checa(perda == 0, f"nó {n}: perda {perda:.2f}% (esperado 0%)")
    vazao = float(l["vazao_mbps"])
    checa(abs(vazao - 5.0) < 0.3, f"nó {n}: vazão {vazao:.2f} Mbps (esperado ~5 Mbps)")
    teorico = float(l["custo_teorico_ms"])
    medido = float(l["atraso_medio_ms"])
    checa(teorico <= medido <= teorico + 2.0,
          f"nó {n}: atraso {medido:.2f} ms entre d={teorico:.0f} e d+2 ms")
    checa(float(sal[n]["atraso_medio_ms"]) >= medido - 1e-6,
          f"nó {n}: Dijkstra ({medido:.2f}) <= menor nº de saltos ({float(sal[n]['atraso_medio_ms']):.2f})  [H1]")

print("\n== Fase 2: difusão")
n_nos = J["num_nodes"]
m = len(J["links"])
esperado_tx = {"mst": n_nos - 1, "spt": n_nos - 1, "flood": 2 * m - (n_nos - 1)}
for modo, tx in esperado_tx.items():
    r = ler(f"difusao_{modo}_resumo.csv")[0]
    checa(float(r["transmissoes_por_msg"]) == tx,
          f"{modo}: {float(r['transmissoes_por_msg']):.0f} transmissões/msg (esperado {tx})  [H2]")
    checa(float(r["entrega_unica_pct"]) == 100, f"{modo}: entrega de 100%")
    checa(int(r["transmissoes_total"]) == int(r["tx_flowmonitor"]),
          f"{modo}: contagem da aplicação = FlowMonitor ({r['tx_flowmonitor']})")
for modo in ("mst", "spt"):
    r = ler(f"difusao_{modo}_resumo.csv")[0]
    checa(float(r["duplicatas_por_msg"]) == 0, f"{modo}: nenhuma duplicata  [H2]")

spt = {int(l["no"]): l for l in ler("difusao_spt_nos.csv")}
mst = {int(l["no"]): l for l in ler("difusao_mst_nos.csv")}
for n in range(1, n_nos):
    a, b = float(spt[n]["atraso_medio_ms"]), float(mst[n]["atraso_medio_ms"])
    checa(b >= a - 1e-6, f"nó {n}: atraso MST ({b:.2f}) >= SPT ({a:.2f})  [H3]")
checa(J["trees"]["mst"]["total_weight_ms"] <= J["trees"]["spt"]["total_weight_ms"],
      f"peso total MST ({J['trees']['mst']['total_weight_ms']}) <= SPT "
      f"({J['trees']['spt']['total_weight_ms']})  [H3]")

ttl = []
for t in range(4, 9):
    caminho = f"difusao_flood_ttl{t}_resumo.csv"
    if os.path.exists(os.path.join(R, caminho)):
        ttl.append(float(ler(caminho)[0]["transmissoes_por_msg"]))
checa(len(ttl) == 5 and all(b > a for a, b in zip(ttl, ttl[1:])),
      f"inundação pura cresce com o TTL: {[int(x) for x in ttl]}")

print()
if falhas:
    print(f"{falhas} verificação(ões) falharam. Não use estes resultados no texto;"
          " envie a saída deste script ao orientador.")
    sys.exit(1)
print("Todas as verificações passaram. Os resultados podem ir para o TCC.")
