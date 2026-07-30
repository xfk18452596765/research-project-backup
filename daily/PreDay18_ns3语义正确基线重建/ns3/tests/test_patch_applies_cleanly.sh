#!/usr/bin/env bash
set -euo pipefail
readonly STAGE_DIR="${1:?stage directory required}"
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
readonly PATCH="$STAGE_DIR/ns3/patches/ns3-3.43-fixed-prmac-access.patch"

if git -C "$WORKTREE" apply --recount --check "$PATCH" 2>/dev/null; then
  echo "clean patch application available"
elif git -C "$WORKTREE" apply --recount --reverse --check "$PATCH"; then
  echo "already applied and safely detected"
else
  echo "patch is neither cleanly applicable nor already applied" >&2
  exit 1
fi
