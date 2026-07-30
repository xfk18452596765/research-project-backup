#!/usr/bin/env bash
set -euo pipefail
readonly STAGE_DIR="${1:?stage directory required}"
readonly SOURCE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"
readonly PATCH="$STAGE_DIR/ns3/patches/ns3-3.43-fixed-prmac-access.patch"
readonly TEMP_ROOT="$(mktemp -d)"
readonly TEMP_TREE="$TEMP_ROOT/ns-3.43"

cleanup() {
  git -C "$SOURCE" worktree remove --force "$TEMP_TREE" >/dev/null 2>&1 || true
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT

git -C "$SOURCE" worktree add --detach "$TEMP_TREE" HEAD
git -C "$TEMP_TREE" apply --recount --check "$PATCH"
git -C "$TEMP_TREE" apply --recount "$PATCH"
if git -C "$TEMP_TREE" apply --recount --check "$PATCH" 2>/dev/null; then
  echo "second patch application unexpectedly succeeded" >&2
  exit 1
fi
git -C "$TEMP_TREE" apply --recount --reverse --check "$PATCH"
git -C "$TEMP_TREE" apply --recount --reverse "$PATCH"
test -z "$(git -C "$TEMP_TREE" status --short)"
echo "patch apply / already-applied detection / reverse roundtrip passed"
