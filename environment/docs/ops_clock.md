# Sample-accurate windows

Authoritative clocks live in `annex29.wav` as embedded marker records: magic
bytes `NUBX`, then a length-prefixed lane name, then big-endian u32 `t0`,
big-endian u32 `t1`, then a length-prefixed `tx` payload. Both sample bounds
use the same endianness. Held-out lanes listed in `suite_meta.json` field
`held_out` (including `L2`) must resolve from the same annex encoding. Scratch
excerpts, generation latch residuals, and dashboard shadow caches must not drive
clocks during synth or certify.
