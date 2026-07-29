#!/usr/bin/env bash
set -euo pipefail
ROOT="/mnt/c/research-project-backup/daily/PreDay18_最小止损路线"
NS3="/home/xfk/workspace/ns-allinone-3.43/ns-3.43"
BIN="$NS3/build/scratch/ns3.43-preday18-dcf-fixed-prmac-default"
RAW="$ROOT/results/ns3/raw"
LOG="$ROOT/logs/ns3_matrix.log"
mkdir -p "$RAW" "$ROOT/results/ns3/aggregate" "$ROOT/results/ns3/traces" "$ROOT/logs"
: >"$LOG"
seeds=(7 17 27 37 47 57 67 77 87 97)
runs=0
for protocol in dcf fixed; do
 for hops in 2 4 6; do
  for load in low medium high; do
   for traffic in periodic poisson; do
    for seed in "${seeds[@]}"; do
     id="ns3-${traffic}-${hops}hop-${load}-seed-${seed}-${protocol}"
     "$BIN" --protocol="$protocol" --traffic="$traffic" --hops="$hops" --load="$load" --seed="$seed" --packets=100 --scenario="$id" --output="$RAW/$id.json" >>"$LOG" 2>&1
     runs=$((runs+1))
    done
   done
  done
 done
done
echo "core_runs=$runs" | tee -a "$LOG"
sensitivity=0
for protocol in dcf fixed; do
 for hops in 4 6; do
  for seed in "${seeds[@]}"; do
   id="ns3-burst-${hops}hop-high-seed-${seed}-${protocol}"; "$BIN" --protocol="$protocol" --traffic=burst --hops="$hops" --load=high --seed="$seed" --packets=100 --scenario="$id" --output="$RAW/$id.json" >>"$LOG" 2>&1; sensitivity=$((sensitivity+1))
  done
 done
 for load in medium high; do
  for scenario in M1 M2; do
   for seed in 7 17 27 37 47; do
    id="ns3-${scenario}-${load}-seed-${seed}-${protocol}"; "$BIN" --protocol="$protocol" --traffic=periodic --hops=6 --load="$load" --seed="$seed" --packets=100 --flows=2 --scenario="$id" --output="$RAW/$id.json" >>"$LOG" 2>&1; sensitivity=$((sensitivity+1))
   done
  done
 done
 for load in medium high; do
  for seed in "${seeds[@]}"; do
   id="ns3-hidden-${load}-seed-${seed}-${protocol}"; "$BIN" --protocol="$protocol" --traffic=poisson --hops=6 --load="$load" --seed="$seed" --packets=100 --hiddenTerminal=1 --scenario="$id" --output="$RAW/$id.json" >>"$LOG" 2>&1; sensitivity=$((sensitivity+1))
  done
 done
 for loss in 0.01 0.05; do
  for seed in "${seeds[@]}"; do
   tag=${loss/./p}; id="ns3-control-${tag}-seed-${seed}-${protocol}"; "$BIN" --protocol="$protocol" --traffic=poisson --hops=6 --load=high --seed="$seed" --packets=100 --controlLoss="$loss" --scenario="$id" --output="$RAW/$id.json" >>"$LOG" 2>&1; sensitivity=$((sensitivity+1))
  done
 done
done
echo "sensitivity_runs=$sensitivity" | tee -a "$LOG"
