#!/usr/bin/env sh
set -eu
stage="$1"; work="$2"
install -D -m 0644 "$stage/ns3/overlay/scratch/preday18-semantic-baseline-v2.cc" "$work/scratch/preday18-semantic-baseline-v2.cc"
