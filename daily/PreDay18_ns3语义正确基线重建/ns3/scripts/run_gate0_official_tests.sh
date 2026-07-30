#!/usr/bin/env bash
set -euo pipefail

readonly STAGE_DIR="${1:?stage directory required}"
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
cd "$WORKTREE"

./ns3 build
./test.py --no-build --jobs 8 --nocolor \
  --text "$STAGE_DIR/logs/ns3_official_tests" \
  --xml "$STAGE_DIR/results/audit/ns3_official_tests"
