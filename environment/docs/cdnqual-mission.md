# Edgekiln mission

Stand up a CDN-edge TCP quality learning kiln.

Pipeline stages (in order):

1. Load the wire map (`run_manifest.json`) and policy (`cdn_policy.json`).
2. Enumerate PCAP files under the active capture root (public by default; `CDNQUAL_CAPTURE_ROOT` overrides).
3. Parse little-endian classic PCAP frames (Ethernet / IPv4 / TCP only).
4. Reassemble each duplex bout under the TCP reassembly contract.
5. Knit the fixed 12-D session feature tensor per bout.
6. Fit intercept-aware L2 ridge weights on labeled public bouts.
7. Score every bout; stamp eval ledger floors and feature digests.

Success means byte-stable artifacts under `/app/qualitycast/` for a fixed wire map.

## Forge packages

Solver-visible Go packages under /app:

- /app/cmd
- /app/framestream
- /app/duplexstitch
- /app/tensorloom
- /app/entropymilli
- /app/l2anvil
- /app/kilnemit
- /app/captureload
- /app/qualityemit
- /app/decoy (specter lure; stay off the forge import graph)
