#!/usr/bin/env bash
set -euo pipefail
readonly STAGE_DIR="${1:?stage directory required}"
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
cd "$WORKTREE"
./ns3 run "scratch/preday18-semantic-baseline --protocol=dcf --scenario=calibration \
--hops=6 --packets=1 --seed=7 \
--output=$STAGE_DIR/results/semantic/calibration-dcf-6hop-1pkt-low-periodic-seed7.json \
--trace=$STAGE_DIR/results/traces/calibration-dcf-6hop-1pkt-low-periodic-seed7.jsonl"
