#!/usr/bin/env bash
# Executa todo o experimento: plano de controle -> 3 cenários de ingestão ->
# 4 cenários de difusão -> varredura de TTL -> análise -> conferência.
#
# Uso:   ./executar_todos.sh /caminho/para/ns-3.44
#        (padrão: ~/workspace/ns-allinone-3.44/ns-3.44)
set -euo pipefail

NS3_DIR="${1:-$HOME/workspace/ns-allinone-3.44/ns-3.44}"
AQUI="$(cd "$(dirname "$0")" && pwd)"
JSON="$AQUI/topologia_ns3.json"
RES="$AQUI/resultados"

if [ ! -x "$NS3_DIR/ns3" ]; then
  echo "ERRO: não encontrei $NS3_DIR/ns3. Informe a pasta do ns-3.44 como argumento." >&2
  exit 1
fi

echo "== 1. Plano de controle (Dijkstra, Kruskal, JSON, figuras 1-5)"
cd "$AQUI"
python3 gerar_topologia.py

echo "== 2. Copiando a simulação para $NS3_DIR/scratch e compilando"
if [ -f "$NS3_DIR/scratch/simulacao.cc" ] && ! cmp -s "$AQUI/simulacao.cc" "$NS3_DIR/scratch/simulacao.cc"; then
  cp "$NS3_DIR/scratch/simulacao.cc" "$NS3_DIR/scratch/simulacao.cc.antigo"
  echo "   (versão anterior salva em scratch/simulacao.cc.antigo)"
fi
cp "$AQUI/simulacao.cc" "$NS3_DIR/scratch/simulacao.cc"
cd "$NS3_DIR"
./ns3 build scratch/simulacao

rm -rf "$RES"
mkdir -p "$RES"

roda() {  # roda <prefixo de saída> <argumentos...>
  local saida="$1"; shift
  ./ns3 run --no-build "scratch/simulacao --json=$JSON --saida=$RES/$saida $*"
}

echo "== 3. Fase 1 — ingestão"
for r in dijkstra saltos global_latencia; do
  roda "ingestao_$r" --fase=ingestao --rota=$r
done

echo "== 4. Fase 2 — difusão"
for m in mst spt flood flood_ttl; do
  roda "difusao_$m" --fase=difusao --modo=$m
done
for t in 4 5 6 7 8; do
  roda "difusao_flood_ttl$t" --fase=difusao --modo=flood_ttl --ttl=$t
done

echo "== 5. Análise (tabelas LaTeX e figuras 6-9)"
cd "$AQUI"
python3 analisar_resultados.py

echo "== 6. Conferência com os valores teóricos"
python3 conferir_resultados.py
