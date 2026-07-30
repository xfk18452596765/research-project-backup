#!/usr/bin/env bash
set -euo pipefail

readonly STAGE_DIR="${1:?stage directory required}"
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
readonly PATCH="$STAGE_DIR/ns3/patches/ns3-3.43-fixed-prmac-access.patch"
readonly OVERLAY="$STAGE_DIR/ns3/overlay"

git -C "$WORKTREE" apply --recount --check "$PATCH"
git -C "$WORKTREE" apply --recount "$PATCH"
cp -a "$OVERLAY/." "$WORKTREE/"
git -C "$WORKTREE" diff --check
git -C "$WORKTREE" status --short
