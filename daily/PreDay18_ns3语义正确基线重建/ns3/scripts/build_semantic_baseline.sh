#!/usr/bin/env bash
set -euo pipefail

readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
cd "$WORKTREE"
./ns3 configure --enable-examples --enable-tests
./ns3 build
./test.py --no-build --constrain=unit
./ns3 build scratch/preday18-semantic-baseline
