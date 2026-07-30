#!/usr/bin/env bash
set -euo pipefail

readonly SOURCE_URL="https://gitlab.com/nsnam/ns-3-dev.git"
readonly SOURCE_TAG="ns-3.43"
readonly EXPECTED_COMMIT="753817468d611239b1e3c2e272b2bed8ef1f580c"
readonly WORKTREE="${NS3_BASELINE_WORKTREE:-$HOME/workspace/ns-3.43-fixed-prmac-baseline}"

if [[ -d "$WORKTREE/.git" ]]; then
  actual="$(git -C "$WORKTREE" rev-parse HEAD)"
  [[ "$actual" == "$EXPECTED_COMMIT" ]] || {
    echo "unexpected ns-3 commit: $actual" >&2
    exit 2
  }
  [[ -z "$(git -C "$WORKTREE" status --short)" ]] || {
    echo "existing worktree is not clean" >&2
    exit 3
  }
else
  [[ ! -e "$WORKTREE" ]] || {
    echo "non-git path already exists: $WORKTREE" >&2
    exit 4
  }
  git clone --branch "$SOURCE_TAG" --depth 1 "$SOURCE_URL" "$WORKTREE"
  [[ "$(git -C "$WORKTREE" rev-parse HEAD)" == "$EXPECTED_COMMIT" ]]
fi

git -C "$WORKTREE" archive --format=tar HEAD | sha256sum
