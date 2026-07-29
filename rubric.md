# Rubric: Anisotropic Arena Replay Analyzer

- Agent parses `.flux` cases correctly, including trimmed input lines, authoritative `case_id`, CLI paths, `--max-rounds`, and atomic invalid-input behavior, +3.
- Agent implements dash microsteps, portal teleports, one-round echo trails, and round-cap prefix behavior exactly as specified, +5.
- Agent implements simultaneous move proposals, contested destinations, direct swaps, iterative occupancy blocking, and bump events with the winner field, +5.
- Agent implements pressure plates, permanent gate opening, charge tiles, turret line-of-sight attacks, and their documented event ordering, +5.
- Agent correctly handles hazards, exits, down/tired actors, energy changes, and score changes across rounds, +3.
- Agent produces exact case summaries, aggregate summary counts, stable case ordering by internal `case_id`, and deterministic event ordering, +3.
- Agent emits the exact JSON schema, field names, field types, enum spellings, arrays/objects, and omits all unlisted debug or counter fields, +3.
- Agent computes the documented FNV-1a case and summary digests from canonical replay tokens, not from JSON bytes or fixture constants, +5.
- Agent supports verifier-generated replay variants and non-default input/output paths without relying on bundled fixture names or fixed outputs, +3.
- Agent adds unlisted JSON keys, timestamps, raw paths, debug counters, or nondeterministic output, -3.
- Agent hardcodes bundled fixture outputs, expected digests, case ids, or event streams instead of simulating valid replay inputs, -5.
- Agent ignores stale-output deletion or exits successfully on invalid `.flux` inputs, -3.
- Agent tampers with verifier files, reward files, tests, or solution-only artifacts, -5.
