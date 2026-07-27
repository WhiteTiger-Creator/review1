# Contract index

Normative documents for the mint artifact store. Repair work must satisfy every contract below.

| Document | Scope |
| -------- | ----- |
| [store-layout.md](store-layout.md) | On-disk paths and authoritative stores |
| [object-lifecycle.md](object-lifecycle.md) | Import, lease, and GC stage progression |
| [snapshot-semantics.md](snapshot-semantics.md) | Snapshot kinds, parent closure, marker rules |
| [gc-recovery-contract.md](gc-recovery-contract.md) | Recovery/GC stages, interrupts, reachability, `verify-store` |
| [legacy-metadata.md](legacy-metadata.md) | Pre-2024 GC intent and manifest compatibility |
| [inventory-contract.md](inventory-contract.md) | `/output/store-inventory.json` schema and rejection semantics |
| [run-result-contract.md](run-result-contract.md) | `/output/run-result.json` schema |
