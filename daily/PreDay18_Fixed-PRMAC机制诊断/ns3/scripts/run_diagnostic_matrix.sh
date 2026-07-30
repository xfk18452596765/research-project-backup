#!/usr/bin/env bash
set -euo pipefail

REPO="/mnt/c/research-project-backup"
ROOT="$REPO/daily/PreDay18_Fixed-PRMAC机制诊断"
NS3="/home/xfk/workspace/ns-allinone-3.43/ns-3.43"
SOURCE="$ROOT/ns3/scratch/preday18-diagnostic-reference.cc"
SCRATCH="$NS3/scratch/preday18-diagnostic-reference.cc"
RAW="$ROOT/results/diagnostic_runs"
TRACES="$ROOT/results/traces"
LOG="$ROOT/logs/ns3_diagnostic_matrix.log"

mkdir -p "$RAW" "$TRACES" "$ROOT/logs"
cp "$SOURCE" "$SCRATCH"
cd "$NS3"
./ns3 build scratch/preday18-diagnostic-reference >"$LOG" 2>&1
BIN=$(find "$NS3/build/scratch" -maxdepth 1 -type f -name '*preday18-diagnostic-reference*' | head -n 1)
test -x "$BIN"

run_case() {
  local mode=$1 protocol=$2 hops=$3 packets=$4 load=$5 traffic=$6 seed=$7 tier=$8
  local id="${tier}-${mode}-${protocol}-${hops}hop-${packets}pkt-${load}-${traffic}-seed${seed}"
  "$BIN" --mode="$mode" --protocol="$protocol" --hops="$hops" --packets="$packets" \
    --load="$load" --traffic="$traffic" --seed="$seed" \
    --trace="$TRACES/$id.jsonl" --output="$RAW/$id.json" >>"$LOG" 2>&1
}

modes=(original causal-forwarding positioned-chain k2-segment reservation-window combined-reference)
protocols=(dcf fixed)

# Tier 1: every protocol/hop must deliver one packet.
for protocol in "${protocols[@]}"; do
  for hops in 1 2 4 6; do
    run_case original "$protocol" "$hops" 1 single periodic 7 tier1
  done
done

# Tier 2: every mode, protocol and low-load hop/seed combination.
for mode in "${modes[@]}"; do
  for protocol in "${protocols[@]}"; do
    for hops in 2 4 6; do
      for seed in 7 17 27; do
        run_case "$mode" "$protocol" "$hops" 10 low periodic "$seed" tier2
      done
    done
  done
done

python3 - "$RAW" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
rows = [json.loads(p.read_text()) for p in root.glob("tier[12]-*.json")]
assert len(rows) == 116, len(rows)
assert all(r["created"] == r["delivered"] for r in rows)
assert all(r["unknown_loss"] == 0 for r in rows)
PY

# Tier 3 runs only after Tier 1/2 gate passes.
for mode in "${modes[@]}"; do
  for protocol in "${protocols[@]}"; do
    for traffic in periodic poisson; do
      for seed in 7 17 27; do
        run_case "$mode" "$protocol" 6 100 high "$traffic" "$seed" tier3
      done
    done
  done
done

echo "tier1_runs=8" >>"$LOG"
echo "tier2_runs=108" >>"$LOG"
echo "tier3_runs=72" >>"$LOG"
echo "total_runs=188" >>"$LOG"

# Same-seed reproducibility probe, kept outside the 188-run diagnostic matrix.
mkdir -p "$ROOT/results/audit/reproducibility"
for replica in a b; do
  "$BIN" --mode=combined-reference --protocol=fixed --hops=2 --packets=10 \
    --load=low --traffic=periodic --seed=7 \
    --trace="$ROOT/results/audit/reproducibility/trace-$replica.jsonl" \
    --output="$ROOT/results/audit/reproducibility/result-$replica.json" >>"$LOG" 2>&1
done
cmp "$ROOT/results/audit/reproducibility/result-a.json" \
    "$ROOT/results/audit/reproducibility/result-b.json"
cmp "$ROOT/results/audit/reproducibility/trace-a.jsonl" \
    "$ROOT/results/audit/reproducibility/trace-b.jsonl"
echo "same_seed_reproducibility=PASS" >>"$LOG"
