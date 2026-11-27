#!/usr/bin/env python3
"""
Análise dos resultados das simulações (executar depois de executar_todos.sh).

Lê resultados/*.csv e topologia_ns3.json e gera:
  tabelas/tab_ingestao.tex      Fase 1 — Dijkstra: rota, custo teórico, medido
  tabelas/tab_rotas.tex         Fase 1 — Dijkstra × menor nº de saltos
  tabelas/tab_difusao.tex       Fase 2 — flood × SPT × MST (totais)
  tabelas/tab_difusao_nos.tex   Fase 2 — atraso por nó, SPT × MST
  figuras/fig6..fig9 (.pdf/.png)
"""
import csv
import glob
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = "resultados"
os.makedirs("tabelas", exist_ok=True)
os.makedirs("figuras", exist_ok=True)

AZUL, VERMELHO, LARANJA, CINZA = "#1f6fd1", "#c0392b", "#c47a12", "#6b6b6b"
TINTA, TINTA2, GRADE = "#1a1a1a", "#555555", "#e4e4e4"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.edgecolor": "#999999", "axes.labelcolor": TINTA,
                     "xtick.color": TINTA2, "ytick.color": TINTA2})

J = json.load(open("topologia_ns3.json", encoding="utf-8"))


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def br(x, casas=2):
    return f"{float(x):.{casas}f}".replace(".", "{,}")


def estilo(ax, ylabel):
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color=GRADE, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def salvar(fig, nome):
    fig.savefig(f"figuras/{nome}.pdf", bbox_inches="tight")
    fig.savefig(f"figuras/{nome}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def seta(rota):
    return r"$\rightarrow$".join(rota.split("-"))


# ===========================================================================
# FASE 1
# ===========================================================================
ing = {r: {int(l["no_origem"]): l for l in ler(f"{R}/ingestao_{r}_fluxos.csv")}
       for r in ("dijkstra", "saltos", "global_latencia")}
nos = sorted(ing["dijkstra"])

# Validação: o roteamento interno do NS-3 (métrica = atraso) = Dijkstra do Python
for n in nos:
    assert ing["dijkstra"][n]["rota"] == ing["global_latencia"][n]["rota"], \
        f"nó {n}: rota NS-3 difere do Dijkstra do Python"

linhas = []
for i, n in enumerate(nos, 1):
    l = ing["dijkstra"][n]
    linhas.append(
        f"Fluxo {i} & Nó {n} & {seta(l['rota'])} & {l['saltos_rota']} & "
        f"{br(l['custo_teorico_ms'], 0)} & {br(l['atraso_medio_ms'])} & "
        f"{l['tx']} / {l['rx']} & {br(l['vazao_mbps'])} & {br(l['perda_pct'])} \\\\")
tab = r"""\begin{table}[h!]
\centering
\caption{Desempenho da Fase de Ingestão com rotas estáticas calculadas por Dijkstra (NS-3.44, FlowMonitor).}
\label{tab:ingestao}
\resizebox{\textwidth}{!}{%
\begin{tabular}{ccccccccc}
\hline
\textbf{Fluxo} & \textbf{Origem} & \textbf{Rota (Dijkstra)} & \textbf{Saltos} & \textbf{$d(v,0)$ (ms)} & \textbf{Atraso medido (ms)} & \textbf{Pacotes (Tx/Rx)} & \textbf{Vazão (Mbps)} & \textbf{Perda (\%)} \\ \hline
""" + "\n".join(linhas) + r"""
\hline
\end{tabular}}
\fonte{Elaborado pelo autor (2026).}
\end{table}
"""
open("tabelas/tab_ingestao.tex", "w", encoding="utf-8").write(tab)

linhas = []
for n in nos:
    d, s = ing["dijkstra"][n], ing["saltos"][n]
    dif = float(s["atraso_medio_ms"]) - float(d["atraso_medio_ms"])
    linhas.append(
        f"Nó {n} & {seta(d['rota'])} & {br(d['atraso_medio_ms'])} & "
        f"{seta(s['rota'])} & {br(s['atraso_medio_ms'])} & "
        f"{'+' if dif > 0.005 else ''}{br(dif)} \\\\")
tab = r"""\begin{table}[h!]
\centering
\caption{Rotas de ingestão: caminho mínimo por atraso (Dijkstra) $\times$ menor número de saltos.}
\label{tab:rotas}
\begin{tabular}{cccccc}
\hline
\textbf{Origem} & \textbf{Rota Dijkstra} & \textbf{Atraso (ms)} & \textbf{Rota menor nº de saltos} & \textbf{Atraso (ms)} & \textbf{Diferença (ms)} \\ \hline
""" + "\n".join(linhas) + r"""
\hline
\end{tabular}
\fonte{Elaborado pelo autor (2026).}
\end{table}
"""
open("tabelas/tab_rotas.tex", "w", encoding="utf-8").write(tab)

# fig6: atraso teórico x medido, Dijkstra x saltos
fig, ax = plt.subplots(figsize=(7.2, 3.8))
x = range(len(nos))
w = 0.38
md = [float(ing["dijkstra"][n]["atraso_medio_ms"]) for n in nos]
ms = [float(ing["saltos"][n]["atraso_medio_ms"]) for n in nos]
td = [float(ing["dijkstra"][n]["custo_teorico_ms"]) for n in nos]
b1 = ax.bar([i - w / 2 - 0.01 for i in x], md, w, color=AZUL, label="Dijkstra (medido)")
b2 = ax.bar([i + w / 2 + 0.01 for i in x], ms, w, color=CINZA, label="Menor nº de saltos (medido)")
ax.scatter([i - w / 2 - 0.01 for i in x], td, marker="_", s=260, color=TINTA, lw=2,
           zorder=3, label="Custo teórico Dijkstra $d(v,0)$")
for i, (a, b) in enumerate(zip(md, ms)):
    ax.text(i - w / 2, a + 0.4, br(a, 1).replace("{,}", ","), ha="center", fontsize=7.5, color=TINTA)
    if abs(a - b) > 0.01:
        ax.text(i + w / 2, b + 0.4, br(b, 1).replace("{,}", ","), ha="center", fontsize=7.5,
                color=TINTA, fontweight="bold")
ax.set_xticks(list(x), [f"Nó {n}" for n in nos])
estilo(ax, "Atraso médio fim a fim (ms)")
ax.set_ylim(0, max(ms) * 1.18)
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_title("Fase 1 — Atraso de ingestão por nó de borda", fontsize=10, color=TINTA)
salvar(fig, "fig6_ingestao_atraso")

# ===========================================================================
# FASE 2
# ===========================================================================
MODOS = [("flood_ttl", "Inundação pura (TTL=4)", CINZA),
         ("flood", "Inundação c/ supressão", LARANJA),
         ("spt", "Árvore SPT (Dijkstra)", AZUL),
         ("mst", "Árvore MST (Kruskal)", VERMELHO)]
res = {m: ler(f"{R}/difusao_{m}_resumo.csv")[0] for m, _, _ in MODOS}
porno = {m: {int(l["no"]): l for l in ler(f"{R}/difusao_{m}_nos.csv")} for m, _, _ in MODOS}

linhas = []
for m, nome, _ in MODOS:
    r = res[m]
    atrasos = [float(l["atraso_medio_ms"]) for l in porno[m].values()]
    linhas.append(
        f"{nome} & {br(r['transmissoes_por_msg'], 0)} & {br(r['duplicatas_por_msg'], 0)} & "
        f"{br(r['entrega_unica_pct'], 0)} & {br(sum(atrasos) / len(atrasos))} & "
        f"{br(max(atrasos))} \\\\")
peso = {m: J["trees"][m]["total_weight_ms"] for m in ("spt", "mst")}
tab = r"""\begin{table}[h!]
\centering
\caption{Desempenho da Fase de Difusão a partir do Sink (450 mensagens de 512 bytes, NS-3.44).}
\label{tab:difusao}
\begin{tabular}{lccccc}
\hline
\textbf{Estratégia} & \textbf{Transmissões/msg} & \textbf{Duplicatas/msg} & \textbf{Entrega (\%)} & \textbf{Atraso médio (ms)} & \textbf{Atraso máximo (ms)} \\ \hline
""" + "\n".join(linhas) + r"""
\hline
\end{tabular}
\fonte{Elaborado pelo autor (2026). Peso total das árvores: SPT = """ + str(peso["spt"]) + \
    r""" ms; MST = """ + str(peso["mst"]) + r""" ms.}
\end{table}
"""
open("tabelas/tab_difusao.tex", "w", encoding="utf-8").write(tab)

linhas = []
for n in range(1, J["num_nodes"]):
    s, k = porno["spt"][n], porno["mst"][n]
    dif = float(k["atraso_medio_ms"]) - float(s["atraso_medio_ms"])
    linhas.append(
        f"{n} & {s['dist_teorica_ms']} & {br(s['atraso_medio_ms'])} & {s['saltos_medios'].split('.')[0]} & "
        f"{k['dist_teorica_ms']} & {br(k['atraso_medio_ms'])} & {k['saltos_medios'].split('.')[0]} & "
        f"{'+' if dif > 0.005 else ''}{br(dif)} \\\\")
tab = r"""\begin{table}[h!]
\centering
\caption{Atraso de difusão por nó receptor: árvore de caminhos mínimos (SPT) $\times$ árvore geradora mínima (MST).}
\label{tab:difusao_nos}
\begin{tabular}{cccccccc}
\hline
 & \multicolumn{3}{c}{\textbf{SPT (Dijkstra)}} & \multicolumn{3}{c}{\textbf{MST (Kruskal)}} & \\
\textbf{Nó} & \textbf{Teórico} & \textbf{Medido} & \textbf{Saltos} & \textbf{Teórico} & \textbf{Medido} & \textbf{Saltos} & \textbf{$\Delta$ (ms)} \\ \hline
""" + "\n".join(linhas) + r"""
\hline
\end{tabular}
\fonte{Elaborado pelo autor (2026). Atrasos em ms.}
\end{table}
"""
open("tabelas/tab_difusao_nos.tex", "w", encoding="utf-8").write(tab)

# fig7: transmissões por mensagem
fig, ax = plt.subplots(figsize=(6.6, 3.6))
vals = [float(res[m]["transmissoes_por_msg"]) for m, _, _ in MODOS]
dups = [float(res[m]["duplicatas_por_msg"]) for m, _, _ in MODOS]
nomes = [n for _, n, _ in MODOS]
cores = [c for _, _, c in MODOS]
ax.barh(nomes, vals, color=cores, height=0.6)
ax.barh(nomes, dups, color="none", height=0.6, hatch="////", edgecolor="white", lw=0)
for i, (v, d) in enumerate(zip(vals, dups)):
    ax.text(v + 0.6, i, f"{v:.0f} transmissões ({d:.0f} duplicatas)", va="center",
            fontsize=8.5, color=TINTA)
ax.axvline(J["num_nodes"] - 1, color=TINTA, lw=1, ls=(0, (3, 3)))
ax.text(J["num_nodes"] - 1, -0.55, " mínimo teórico |V|−1 = 11", fontsize=8, color=TINTA2, va="bottom")
ax.invert_yaxis()
ax.set_ylim(len(MODOS) - 0.5, -0.9)
ax.set_xlim(0, max(vals) * 1.55)
ax.grid(axis="x", color=GRADE, lw=0.8)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.set_xlabel("Transmissões por mensagem difundida (hachurado = duplicatas)")
ax.set_title("Fase 2 — Custo de difusão por estratégia", fontsize=10, color=TINTA)
salvar(fig, "fig7_difusao_transmissoes")

# fig8: tempestade de difusão em função do TTL
ttl = []
for f in glob.glob(f"{R}/difusao_flood_ttl[0-9]*_resumo.csv"):
    t = int(re.search(r"ttl(\d+)_", f).group(1))
    ttl.append((t, float(ler(f)[0]["transmissoes_por_msg"])))
if ttl:
    ttl.sort()
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    ax.plot([t for t, _ in ttl], [v for _, v in ttl], color=CINZA, lw=2, marker="o", ms=7,
            label="Inundação pura")
    ax.plot([t for t, _ in ttl], [J["theory"]["tx_per_message_flood"]] * len(ttl),
            color=LARANJA, lw=2, marker="s", ms=7, label="Inundação c/ supressão")
    ax.plot([t for t, _ in ttl], [J["num_nodes"] - 1] * len(ttl), color=VERMELHO, lw=2,
            marker="D", ms=7, label="Árvore (SPT ou MST)")
    for t, v in ttl:
        ax.annotate(f"{v:.0f}", (t, v), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, color=TINTA)
    ax.set_xticks([t for t, _ in ttl])
    ax.set_xlabel("TTL inicial")
    estilo(ax, "Transmissões por mensagem")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("Tempestade de difusão: crescimento com o TTL", fontsize=10, color=TINTA)
    salvar(fig, "fig8_tempestade_ttl")

# fig9: atraso por nó na difusão, SPT x MST
fig, ax = plt.subplots(figsize=(7.2, 3.8))
rec = list(range(1, J["num_nodes"]))
vs = [float(porno["spt"][n]["atraso_medio_ms"]) for n in rec]
vm = [float(porno["mst"][n]["atraso_medio_ms"]) for n in rec]
w = 0.38
ax.bar([i - w / 2 - 0.01 for i in range(len(rec))], vs, w, color=AZUL, label="SPT (Dijkstra)")
ax.bar([i + w / 2 + 0.01 for i in range(len(rec))], vm, w, color=VERMELHO, label="MST (Kruskal)")
for i, (a, b) in enumerate(zip(vs, vm)):
    if b - a > 0.01:
        ax.text(i + w / 2, b + 0.4, f"+{b - a:.0f}", ha="center", fontsize=8, color=TINTA,
                fontweight="bold")
ax.set_xticks(range(len(rec)), [str(n) for n in rec])
ax.set_xlabel("Nó receptor")
estilo(ax, "Atraso Sink → nó (ms)")
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_title("Fase 2 — Atraso de difusão por nó: SPT × MST", fontsize=10, color=TINTA)
salvar(fig, "fig9_difusao_atraso_nos")

print("Tabelas em ./tabelas e figuras fig6–fig9 em ./figuras")
for m, nome, _ in MODOS:
    print(f"  {nome:28s} {res[m]['transmissoes_por_msg']:>5} tx/msg  "
          f"{res[m]['duplicatas_por_msg']:>5} dup/msg")
