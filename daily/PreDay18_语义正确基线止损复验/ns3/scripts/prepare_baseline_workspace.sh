#!/usr/bin/env bash
set -euo pipefail
readonly SOURCE="${1:?generated source required}"
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
readonly EXPECTED_COMMIT="753817468d611239b1e3c2e272b2bed8ef1f580c"
[[ "$(git -C "$WORKTREE" rev-parse HEAD)" == "$EXPECTED_COMMIT" ]]
cp "$SOURCE" "$WORKTREE/scratch/preday18-stop-loss-retest.cc"
cd "$WORKTREE"
./ns3 build scratch_preday18-stop-loss-retest
