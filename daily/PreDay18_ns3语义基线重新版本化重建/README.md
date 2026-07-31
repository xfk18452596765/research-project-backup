# Semantic Baseline V2

This is a new, independently versioned ns-3.43 baseline. It does not restore or
claim authority for the historical P1 or any historical patched source tree.

Historical results are retained unchanged. The old patch-chain reproducibility
is incomplete and historical P1 authority is unavailable.

`run_v2_audit.py` is intentionally fail-closed: a READY decision is impossible
unless a clean official ns-3.43 source, a complete overlay, a standard patch,
two independent A/B rebuilds, and all required empirical gate evidence exist.
Day18 remains LOCKED and RL is not run by this stage.
