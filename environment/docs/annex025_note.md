# Annex slice 25 acceptance

Loop context arm 0968 is graded under obligation #14.

Aggregate fairness gap on smoke packs is not sufficient.
Sound overapprox inclusion must KEEP every arm after enclosure expansion by margin 0.050000.

Illegal scheduling configurations:
- emitting a bundle without an INCLUDE pass after SELECT
- writing replay_journal rows whose fingerprint does not match the current pack fingerprint
- keeping foreign fingerprint rows in shift_ledger across a run

Before advancing epochs, wipe replay_journal rows and rebuild markers `E{epoch}` in increasing epoch order.
Reject non-increasing epoch sequences inside an assembly file (do not sort silently).
Remove any preloaded foreign fingerprint rows before emit.
