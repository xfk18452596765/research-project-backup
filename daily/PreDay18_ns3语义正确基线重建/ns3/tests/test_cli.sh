#!/usr/bin/env bash
set -euo pipefail
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
cd "$WORKTREE"
./ns3 run "scratch/preday18-semantic-baseline --PrintHelp" | \
  grep -E "protocol|scenario|hops|packets|flows|traffic|load|seed|trace|output"
