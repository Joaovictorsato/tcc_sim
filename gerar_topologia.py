#!/usr/bin/env python3
"""
Plano de Controle — Abordagem híbrida Dijkstra (ingestão) + Kruskal (difusão)

Gera, a partir da topologia física (Tabela 3 do TCC):
  1. Caminhos mínimos de cada nó até o Sink (Dijkstra, peso = atraso em ms)
     e a Árvore de Caminhos Mínimos (SPT) resultante;
  2. Caminhos de menor número de saltos (BFS) — linha de base;
  3. A Árvore Geradora Mínima (Kruskal, implementado passo a passo com
     Union-Find) e a ordem em que cada aresta foi aceita/rejeitada;
  4. Valores teóricos esperados (atraso por nó em cada árvore, nº de
     transmissões por mensagem em flooding/SPT/MST);
  5. O arquivo topologia_ns3.json consumido pelo simulacao.cc;
  6. Figuras ilustrativas (PDF para o LaTeX + PNG) em ./figuras.

Uso:  python3 gerar_topologia.py
Requer: networkx, matplotlib
"""
import json
import os
from collections import deque

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

SAIDA_JSON = "topologia_ns3.json"
DIR_FIG = "figuras"
SINK = 0

# ---------------------------------------------------------------------------
# 1. Topologia física (Tabela 3): (u, v, tipo, banda Mbps, atraso ms)
# ---------------------------------------------------------------------------
ENLACES = [
   (0, 1, "core", 100, 2),
    (0, 4, "core", 100, 3),
    (1, 2, "core", 100, 4),
    (1, 4, "core", 100, 2),
    (2, 3, "core", 100, 5),
    (2, 5, "core", 100, 3),
    (4, 5, "core", 100, 4),
    (3, 5, "core", 100, 2),
    (4, 6, "edge", 50, 10),
    (4, 7, "edge", 10, 15),
    (4, 8, "edge", 10, 20),
    (5, 9, "edge", 50, 10),
    (5, 10, "edge", 20, 12),
    (3, 11, "edge", 10, 18),
]
NOS_BORDA = [6, 7, 8, 9, 10, 11]
#===========cenariotemporario================
#ENLACES = [
#   (0, 1, "edge", 100, 2),
#    (0, 4, "edge", 100, 3),
#    (1, 2, "edge", 100, 4),
#    (1, 4, "edge", 100, 2),
#    (2, 3, "edge", 100, 5),
#    (2, 5, "core", 100, 3),
#    (4, 5, "core", 100, 4),
#    (3, 5, "core", 100, 2),
#    (4, 6, "core", 50, 10),
#    (4, 7, "core", 10, 15),
#    (4, 8, "core", 10, 20),
#    (5, 9, "core", 50, 10),
#    (5, 10, "core", 20, 12),
#    (3, 11, "core", 10, 18),
#]
#NOS_BORDA = [1, 2, 3, 4, 5, 6]

#=============cenario2===========
#ENLACES = [
#    (0, 1, "core", 100, 2),
#    (0, 2, "core", 100, 8),
#    (1, 2, "core", 100, 3),
#    (1, 3, "edge", 50, 5),
#    (2, 4, "edge", 20, 10),
#    (2, 5, "edge", 10, 15),
#    (1, 4, "edge", 20, 18),
#]
#NOS_BORDA = [3, 4, 5]
#=============cenario3================
#ENLACES = [
#    (0, 1, "core", 100, 2),
#    (0, 2, "core", 100, 3),
#    (1, 2, "core", 100, 2),
#    (1, 3, "core", 100, 3),
#    (2, 4, "core", 100, 2),
#    (3, 4, "core", 100, 4),
#   (3, 5, "core", 100, 2),
#   (4, 6, "core", 100, 3),
#    (5, 6, "core", 100, 2),
#   (5, 7, "core", 100, 3),
#    (6, 8, "core", 100, 2),
#    (7, 9, "core", 100, 2),
#    (8, 9, "core", 100, 3),
#    (0, 5, "core", 50, 15),
#    (0, 9, "core", 50, 25),
#    (2, 8, "core", 50, 12),
#    (1, 10, "edge", 20, 8),
#    (2, 11, "edge", 20, 10),
#    (3, 12, "edge", 50, 6),
#    (4, 13, "edge", 10, 12),
#    (5, 14, "edge", 20, 8),
#    (6, 15, "edge", 10, 15),
#    (7, 16, "edge", 50, 7),
#    (8, 17, "edge", 20, 10),
#    (9, 18, "edge", 10, 18),
 #   (9, 19, "edge", 20, 12),
 #   (2, 14, "edge", 20, 20),
 #   (4, 17, "edge", 20, 18),
#]
#NOS_BORDA = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
G = nx.Graph()
#G.add_nodes_from(range(12))
G.add_nodes_from(sorted({
    n for u, v, tipo, bw, d in ENLACES
    for n in (u, v)
}))

for i, (u, v, tipo, bw, d) in enumerate(ENLACES):
    G.add_edge(u, v, weight=d, bw=bw, tipo=tipo, idx=i)


def chave(u, v):
    return (min(u, v), max(u, v))


# ---------------------------------------------------------------------------
# 2. Dijkstra (fonte única = Sink). Como o grafo é não orientado, a árvore
#    de caminhos mínimos enraizada no Sink dá, para cada nó, o caminho
#    mínimo nó -> Sink (basta ler o caminho de trás para frente).
# ---------------------------------------------------------------------------
dist_spt, cam_spt = nx.single_source_dijkstra(G, SINK, weight="weight")
pai_spt = {v: (cam_spt[v][-2] if v != SINK else None) for v in G}
arestas_spt = sorted(chave(v, p) for v, p in pai_spt.items() if p is not None)
rotas_dijkstra = {v: list(reversed(cam_spt[v])) for v in G if v != SINK}

# Linha de base: menor número de saltos (BFS, ignora atrasos)
cam_bfs = nx.single_source_shortest_path(G, SINK)
rotas_saltos = {v: list(reversed(cam_bfs[v])) for v in G if v != SINK}


def custo(rota):
    return sum(G[a][b]["weight"] for a, b in zip(rota, rota[1:]))


# ---------------------------------------------------------------------------
# 3. Kruskal implementado explicitamente (Union-Find com compressão de
#    caminho e união por posto) para registrar cada passo.
# ---------------------------------------------------------------------------
pai_uf = list(range(G.number_of_nodes()))
posto = [0] * G.number_of_nodes()


def find(x):
    while pai_uf[x] != x:
        pai_uf[x] = pai_uf[pai_uf[x]]
        x = pai_uf[x]
    return x


def union(a, b):
    ra, rb = find(a), find(b)
    if posto[ra] < posto[rb]:
        ra, rb = rb, ra
    pai_uf[rb] = ra
    if posto[ra] == posto[rb]:
        posto[ra] += 1


passos_kruskal = []
arestas_mst = []
for u, v, d in sorted(((u, v, d) for u, v, _, _, d in ENLACES),
                      key=lambda e: (e[2], e[0], e[1])):
    aceita = find(u) != find(v)
    if aceita:
        union(u, v)
        arestas_mst.append(chave(u, v))
    passos_kruskal.append({"aresta": [u, v], "peso": d, "aceita": aceita})
arestas_mst.sort()

# Conferência com a implementação da NetworkX
mst_nx = sorted(chave(u, v) for u, v in
                nx.minimum_spanning_tree(G, algorithm="kruskal").edges())
assert mst_nx == arestas_mst, "Kruskal próprio difere da NetworkX!"

T_mst = G.edge_subgraph(arestas_mst).copy()
dist_mst, cam_mst = nx.single_source_dijkstra(T_mst, SINK, weight="weight")
pai_mst = {v: (cam_mst[v][-2] if v != SINK else None) for v in G}


def filhos(pai):
    f = {v: [] for v in G}
    for v, p in pai.items():
        if p is not None:
            f[p].append(v)
    return {v: sorted(c) for v, c in f.items()}


# ---------------------------------------------------------------------------
# 4. Valores teóricos
# ---------------------------------------------------------------------------
n, m = G.number_of_nodes(), G.number_of_edges()
tx_arvore = n - 1                         # uma transmissão por aresta da árvore
tx_flood = sum(G.degree(v) - (0 if v == SINK else 1) for v in G)  # = 2m-(n-1)
peso_spt = sum(G[u][v]["weight"] for u, v in arestas_spt)
peso_mst = sum(G[u][v]["weight"] for u, v in arestas_mst)
peso_total = sum(d for *_, d in ENLACES)

# ---------------------------------------------------------------------------
# 5. Exporta JSON para o NS-3
# ---------------------------------------------------------------------------
dados = {
    "num_nodes": n,
    "sink_node": SINK,
    "links": [{"id": i, "src": u, "dst": v, "type": t, "bw_mbps": bw,
               "delay_ms": d, "weight": d}
              for i, (u, v, t, bw, d) in enumerate(ENLACES)],
    "edge_nodes": NOS_BORDA,
    "ingestion": {
        "dijkstra_paths": {str(k): r for k, r in rotas_dijkstra.items()},
        "dijkstra_cost_ms": {str(k): dist_spt[k] for k in rotas_dijkstra},
        "min_hops_paths": {str(k): r for k, r in rotas_saltos.items()},
        "min_hops_cost_ms": {str(k): custo(r) for k, r in rotas_saltos.items()},
    },
    "trees": {
        "spt": {"edges": [list(e) for e in arestas_spt],
                "children": {str(k): c for k, c in filhos(pai_spt).items()},
                "total_weight_ms": peso_spt,
                "dist_from_sink_ms": {str(k): dist_spt[k] for k in G}},
        "mst": {"edges": [list(e) for e in arestas_mst],
                "children": {str(k): c for k, c in filhos(pai_mst).items()},
                "total_weight_ms": peso_mst,
                "dist_from_sink_ms": {str(k): dist_mst[k] for k in G},
                "kruskal_steps": passos_kruskal},
    },
    "theory": {"tx_per_message_tree": tx_arvore,
               "tx_per_message_flood": tx_flood,
               "graph_total_weight_ms": peso_total},
}
with open(SAIDA_JSON, "w", encoding="utf-8") as f:
    json.dump(dados, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# 6. Figuras
# ---------------------------------------------------------------------------
os.makedirs(DIR_FIG, exist_ok=True)
POS = {0: (4.8, 7.4), 1: (2.8, 6.2), 4: (6.8, 6.2), 2: (2.8, 4.3),
       5: (6.8, 4.3), 3: (4.8, 3.1), 6: (9.0, 7.4), 7: (9.3, 6.2),
       8: (9.0, 5.0), 9: (9.0, 3.6), 10: (8.0, 2.3), 11: (4.8, 1.5)}
#=================cenario2==============================================
#POS = {
 #   0: (4.0, 7.0),
  #  1: (2.0, 5.0),
 #   2: (6.0, 5.0),
 #   3: (0.5, 3.0),
 #  4: (4.0, 2.0),
 #   5: (7.5, 3.0),
#}
#============================cenario3==================
#POS = {
#    0: (5.8, 7.4),
#    1: (4.3, 6.4),
#    2: (7.3, 6.4),
#    3: (4.3, 5.4),
#    4: (7.3, 5.4),
#    5: (4.3, 4.4),
#    6: (7.3, 4.4),
#    7: (4.3, 3.4),
#    8: (7.3, 3.4),
#    9: (5.8, 2.4),
#    10: (2.4, 6.9),
#    11: (9.2, 6.9),
#    12: (2.4, 5.4),
#    13: (9.2, 5.4),
#    14: (2.4, 4.4),
#    15: (9.2, 4.4),
#    16: (2.4, 3.4),
#    17: (9.2, 3.4),
#    18: (4.7, 1.4),
#    19: (6.9, 1.4),
#}

COR_NO = {"sink": "#9ec5f0", "core": "#f6dc86", "edge": "#a9d8a0"}
AZUL, VERMELHO, ROXO, CINZA = "#1f6fd1", "#c0392b", "#7b3fa0", "#b5b5b5"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})


def tipo_no(v):
    return "sink" if v == SINK else ("edge" if v in NOS_BORDA else "core")


def desenhar_base(ax, rotulos_dist=None, largura_core=True):
    ax.set_xlim(1.9, 10.4)
    ax.set_ylim(0.8, 8.1)
    ax.set_aspect("equal")
    ax.axis("off")
    cores = [COR_NO[tipo_no(v)] for v in G]
    nx.draw_networkx_nodes(G, POS, ax=ax, node_color=cores, node_size=620,
                           edgecolors="#333333", linewidths=1.2)
    rot = {v: ("S" if v == SINK else str(v)) for v in G}
    rot[SINK] = "0"
    nx.draw_networkx_labels(G, POS, rot, ax=ax, font_weight="bold",
                            font_size=11)
    if rotulos_dist:
        for v, txt in rotulos_dist.items():
            x, y = POS[v]
            ax.text(x + 0.36, y - 0.30, txt, ha="left", va="top", fontsize=8,
                    color="#1a1a1a",
                    bbox=dict(boxstyle="round,pad=0.12", fc="#ffffffd0", ec="none"))


def desenhar_arestas(ax, destaque=None, cor="#333333", direcionado_pai=None,
                     sentido="para_raiz", outras="tracejado", pesos=True,
                     extras=None):
    """destaque: conjunto de arestas em evidência; extras: {aresta: cor}."""
    destaque = destaque or set()
    extras = extras or {}
    for u, v in G.edges():
        k = chave(u, v)
        w = G[u][v]["weight"]
        if k in extras:
            nx.draw_networkx_edges(G, POS, [(u, v)], ax=ax, width=3.2,
                                   edge_color=extras[k])
        elif k in destaque:
            if direcionado_pai is not None:
                filho = v if direcionado_pai.get(v) == u else u
                pai = u if filho == v else v
                a, b = (filho, pai) if sentido == "para_raiz" else (pai, filho)
                nx.draw_networkx_edges(G, POS, [(a, b)], ax=ax, width=3.2,
                                       edge_color=cor, arrows=True,
                                       arrowstyle="-|>", arrowsize=16,
                                       node_size=620)
            else:
                nx.draw_networkx_edges(G, POS, [(u, v)], ax=ax, width=3.2,
                                       edge_color=cor)
        elif outras == "tracejado":
            nx.draw_networkx_edges(G, POS, [(u, v)], ax=ax, width=1.2,
                                   edge_color=CINZA, style=(0, (4, 3)))
        else:
            larg = 2.6 if G[u][v]["tipo"] == "core" else 1.4
            nx.draw_networkx_edges(G, POS, [(u, v)], ax=ax, width=larg,
                                   edge_color="#444444")
        if pesos:
            x = (POS[u][0] + POS[v][0]) / 2
            y = (POS[u][1] + POS[v][1]) / 2
            ax.text(x, y, f"{w}", fontsize=8.5, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white",
                              ec="none", alpha=0.9))


def legenda_nos(ax, extra=()):
    from matplotlib.lines import Line2D
    h = [Line2D([], [], marker="o", ls="", ms=10, mfc=COR_NO["sink"],
                mec="#333", label="Sink (nó 0)"),
         Line2D([], [], marker="o", ls="", ms=10, mfc=COR_NO["core"],
                mec="#333", label="Núcleo (1–5)"),
         Line2D([], [], marker="o", ls="", ms=10, mfc=COR_NO["edge"],
                mec="#333", label="Borda (6–11)")]
    h += list(extra)
    ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, 0.0),
              ncol=3, fontsize=8, frameon=False)


def salvar(fig, nome):
    fig.savefig(os.path.join(DIR_FIG, nome + ".pdf"), bbox_inches="tight")
    fig.savefig(os.path.join(DIR_FIG, nome + ".png"), dpi=200,
                bbox_inches="tight")
    plt.close(fig)


from matplotlib.lines import Line2D

# 6.1 Grafo original
fig, ax = plt.subplots(figsize=(6.4, 5.4))
desenhar_base(ax)
desenhar_arestas(ax, outras="solido")
legenda_nos(ax, [Line2D([], [], color="#444", lw=2.6, label="Enlace de núcleo (100 Mbps)"),
                 Line2D([], [], color="#444", lw=1.4, label="Enlace de borda (10–50 Mbps)")])
ax.set_title(f"Grafo G = (V, E, w): |V| = {n}, |E| = {m}, peso = atraso (ms)",
             fontsize=10)
salvar(fig, "fig1_grafo_original")

# 6.2 Árvore de caminhos mínimos (Dijkstra) — setas no sentido da ingestão
fig, ax = plt.subplots(figsize=(6.4, 5.4))
desenhar_base(ax, {v: f"d={dist_spt[v]}" for v in G if v != SINK})
desenhar_arestas(ax, set(arestas_spt), AZUL, pai_spt, "para_raiz")
legenda_nos(ax, [Line2D([], [], color=AZUL, lw=3, label="Aresta da SPT (rota de ingestão)"),
                 Line2D([], [], color=CINZA, lw=1.2, ls="--", label="Enlace não usado")])
ax.set_title(f"Dijkstra: árvore de caminhos mínimos até o Sink "
             f"(Σw = {peso_spt} ms)", fontsize=10)
salvar(fig, "fig2_dijkstra_spt")

# 6.3 Kruskal passo a passo (6 quadros)
#quadros = [2, 4, 6, 8, 11, len(passos_kruskal)]
total_passos = len(passos_kruskal)

quadros = sorted({
    max(1, (i * total_passos + 5) // 6)
    for i in range(1, 7)
}) if total_passos > 0 else []
fig, axs = plt.subplots(2, 3, figsize=(13, 9.6))
for ax in list(axs.flat)[len(quadros):]:
    ax.set_visible(False)
for ax, k in zip(axs.flat, quadros):
    aceitas = {chave(*p["aresta"]) for p in passos_kruskal[:k] if p["aceita"]}
    rejeit = {chave(*p["aresta"]) for p in passos_kruskal[:k] if not p["aceita"]}
    atual = passos_kruskal[k - 1]
    extras = {e: "#e8a39b" for e in rejeit}
    desenhar_base(ax)
    desenhar_arestas(ax, aceitas, VERMELHO, extras=extras)
    u, v = atual["aresta"]
    estado = "aceita" if atual["aceita"] else "REJEITADA (formaria ciclo)"
    ax.set_title(f"Passo {k}/{len(passos_kruskal)}: aresta ({u},{v}), "
                 f"w={atual['peso']} → {estado}\n|E_T| = {len(aceitas)}",
                 fontsize=9.5)
fig.legend(handles=[Line2D([], [], color=VERMELHO, lw=3, label="Aceita na MST"),
                    Line2D([], [], color="#e8a39b", lw=3, label="Rejeitada (ciclo)"),
                    Line2D([], [], color=CINZA, lw=1.2, ls="--", label="Ainda não processada")],
           loc="lower center", ncol=3, fontsize=10)
fig.suptitle("Execução do Algoritmo de Kruskal (arestas em ordem não decrescente de peso)",
             fontsize=12)
fig.tight_layout(rect=(0, 0.04, 1, 0.97), h_pad=3.0)
salvar(fig, "fig3_kruskal_passos")

# 6.4 MST — setas no sentido da difusão (Sink -> folhas)
fig, ax = plt.subplots(figsize=(6.4, 5.4))
desenhar_base(ax, {v: f"d={dist_mst[v]}" for v in G if v != SINK})
desenhar_arestas(ax, set(arestas_mst), VERMELHO, pai_mst, "da_raiz")
legenda_nos(ax, [Line2D([], [], color=VERMELHO, lw=3, label="Aresta da MST (difusão)"),
                 Line2D([], [], color=CINZA, lw=1.2, ls="--", label="Removida por Kruskal")])
ax.set_title(f"Kruskal: Árvore Geradora Mínima (Σw = {peso_mst} ms)",
             fontsize=10)
salvar(fig, "fig4_kruskal_mst")

# 6.5 Comparação SPT x MST
comuns = set(arestas_spt) & set(arestas_mst)
so_spt = set(arestas_spt) - set(arestas_mst)
so_mst = set(arestas_mst) - set(arestas_spt)
fig, ax = plt.subplots(figsize=(6.4, 5.4))
rot = {v: (f"{dist_spt[v]}|{dist_mst[v]}") for v in G if v != SINK}
desenhar_base(ax, rot)
desenhar_arestas(ax, comuns, ROXO,
                 extras={**{e: AZUL for e in so_spt}, **{e: VERMELHO for e in so_mst}})
legenda_nos(ax, [Line2D([], [], color=ROXO, lw=3, label="Comum às duas árvores"),
                 Line2D([], [], color=AZUL, lw=3, label="Só na SPT (Dijkstra)"),
                 Line2D([], [], color=VERMELHO, lw=3, label="Só na MST (Kruskal)")])
ax.set_title("SPT × MST — rótulo: atraso até o Sink SPT|MST (ms)", fontsize=10)
salvar(fig, "fig5_spt_vs_mst")

# ---------------------------------------------------------------------------
# Relatório no terminal
# ---------------------------------------------------------------------------
print("=== Dijkstra (ingestão) ===")
for v in NOS_BORDA:
    r, rs = rotas_dijkstra[v], rotas_saltos[v]
    print(f"  nó {v:2d}: {' -> '.join(map(str, r)):18s} {dist_spt[v]:3d} ms"
          f" | menor nº saltos: {' -> '.join(map(str, rs)):18s} {custo(rs):3d} ms")
print(f"  SPT: {arestas_spt}  Σw = {peso_spt}")
print("=== Kruskal (difusão) ===")
for i, p in enumerate(passos_kruskal, 1):
    print(f"  {i:2d}. {tuple(p['aresta'])} w={p['peso']:2d} "
          f"{'aceita' if p['aceita'] else 'rejeitada (ciclo)'}")
print(f"  MST: {arestas_mst}  Σw = {peso_mst}  (grafo: {peso_total})")
print(f"=== Transmissões por mensagem: árvore = {tx_arvore}, "
      f"flooding = {tx_flood} ===")
print(f"Arquivos: {SAIDA_JSON}, {DIR_FIG}/fig1..fig5 (.pdf/.png)")
