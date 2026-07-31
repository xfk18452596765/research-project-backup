# P1 semantic baseline patch applicability recovery

This append-only stage audits the canonical Git blob and fails closed unless an
authoritative complete semantic patched tree can be reconstructed without editing
the damaged historical P1 or using `--recount`.
