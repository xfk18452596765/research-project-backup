# Fixed-PRMAC failure attribution reinforcement

This evidence-only stage replays only DCF and F0 with frozen parameters.  It does not implement C1/C2/C3, modify historic evidence, start Day18, or run RL.

Run, in order: `python code/run_attribution_audit.py`, `python code/run_attribution_replay.py`, then `python code/run_attribution_closure.py`.
