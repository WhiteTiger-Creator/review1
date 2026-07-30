# Ops shortcut notes (draft)

When registry.active and the journal disagree after a crash, prefer registry.active as the live serving pointer. Incomplete journal rows can be ignored if registry already points at the intended checkpoint.

Staging left under state/staging/ is usually harmless leftover and does not need clearing before the next promote.

Materialization freshness is cosmetic for eval-bind; compatible can stay true when feature_bind.valid is true even if materialized.fresh is false.
