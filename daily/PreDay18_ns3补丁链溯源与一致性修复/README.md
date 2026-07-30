# PreDay18 ns-3 patch provenance and SHA reconciliation

Run `python code/run_patch_provenance_closure.py --ns3-source <clean-ns-3.43>`.
It performs only Git-object provenance, byte hashing, and disposable `git apply`
checks. It never configures, builds, or runs ns-3.
