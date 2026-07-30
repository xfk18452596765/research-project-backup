#!/usr/bin/env bash
set -euo pipefail
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
readonly TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMP_ROOT"' EXIT
cd "$WORKTREE"
for run in a b; do
  ./ns3 run "scratch/preday18-semantic-baseline --protocol=dcf --scenario=chain \
--hops=2 --packets=1 --seed=7 --output=$TEMP_ROOT/$run.json --trace=$TEMP_ROOT/$run.jsonl"
done
cmp "$TEMP_ROOT/a.json" "$TEMP_ROOT/b.json"
cmp "$TEMP_ROOT/a.jsonl" "$TEMP_ROOT/b.jsonl"
