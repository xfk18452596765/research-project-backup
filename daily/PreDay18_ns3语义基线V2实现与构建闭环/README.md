# Semantic Baseline V2 implementation and build closure

This stage uses two separately cloned official ns-3.43 workspaces. The overlay
contains a real ns-3 Wi-Fi DCF smoke executable with physical chain positions,
802.11b data/basic rates, and no application-layer reservation staggering.
It is not yet a Fixed-PRMAC V2 implementation: no reservation state has been
wired into a local Wi-Fi MAC access-path component. The result must therefore
remain HOLD, rather than misrepresenting a scratch program as MAC protection.
