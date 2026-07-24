# Rollout Profile Overlay

Site overlays may tighten freeze evaluation so the freeze window is closed at the end
timestamp (`reference_time <= freeze_window_end`). Dashboard mirrors historically used
that closed interval when projecting maintenance freezes.

When `chain_mode` is `canonical`, metadata chain hashes are computed over
canonical re-serialization of the parsed document rather than raw on-disk bytes.
That mode keeps chain digests stable across pretty-print regenerations of the same
logical metadata.

Duplicate keyids encountered during signature evaluation are retired after the first
attempt for that keyid so counting stays O(n) for large signature arrays.
