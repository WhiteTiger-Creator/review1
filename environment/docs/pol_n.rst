# Fatigue algebra and degradation obligation (pol_n)

Public obligation for every regenerated observation set and rights sheet.

0. Instantaneous estimate. For a channel with trajectory vector `tr` of length
   `n`, slope `sl`, and epoch index `e` in `0 .. n-1`, define
   `raw(e) = mean(tr[0 .. e]) - sl * e` where `mean` is the arithmetic mean of
   the inclusive prefix `tr[0], ..., tr[e]`. Then `s(e) = max(0, raw(e))`.

1. Class ladder. With descending cuts `cuts[0] > cuts[1] > cuts[2]`:
   `c(e) = 0` if `s(e) >= cuts[0]`;
   else `1` if `s(e) >= cuts[1]`;
   else `2` if `s(e) >= cuts[2]`;
   else `3`.

2. Folded band. `B[e] = round_half_up(s(e), 6)` meaning scale by `1e6`, round
   half away from zero to nearest integer, then divide by `1e6`. Class `c(e)` is
   evaluated on `raw(e)` before that rounding step.

3. Resolution cache and campaign journal. A fold may keep an opaque map from
   epoch index to band. Under `<root>/var/journal/<sid>.json` the desk may persist
   `{gen, bands, cls, q}` for a channel. When a pack has `mode >= 1` and a journal
   record exists for that `sid` with `gen` equal to the pack `gen` field (default
   `0` when omitted), the fold may seed its epoch cache from journal `bands`, and
   the budget path may see journal `q` as a prior vector. After seeding, outputs
   must still match a cold fold with an empty cache: when `e > 0` and
   `c(e) != c(e-1)`, every cache entry must be discarded and every band for
   epochs `0 .. e` must be recomputed before continuing. No journal-seeded band
   may survive a class transition. A final consistency requirement: every emitted
   `B[e]` must equal the cold-fold band for that epoch.

4. Fatigue budget. From bands `B` and per-epoch ladder values `c`, define
   `Q[0] = 0` and for `i = 1 .. len(B)-1`:
   `cost(i) = abs(B[i] - B[i-1]) / (1 + max(c[i], c[i-1]))`,
   `Q[i] = Q[i-1] + cost(i) * (0.97 ** i)`.
   On every call, including campaign replay (`mode >= 1`), `Q` must be recomputed
   from the current `B` and `c`. A journal prior vector must not be returned as
   `Q`, even when lengths match and the prior is non-zero.

5. Alert flood mark. Set `fld = 1` if any `i >= 1` has
   `cost(i) > 0.15` and `max(c[i], c[i-1]) >= 2`; else `fld = 0`.

6. Access grants. For each channel `sid`, field `acc` is the string `full` when
   `max_e c(e) < 2`, otherwise `limited`. A single healthy early epoch does not
   keep the grant at `full` once any later epoch reaches class 2 or higher.

7. Non-goals. Let `S` be the set of distinct ladder values `>= 2` observed across
   all channels in a regenerated observation root, including classes that appear
   only after a class transition inside a channel. The rights sheet `neg` array
   must contain exactly the tokens `ng:{k}` for each `k` in `S`, sorted
   ascending by `k`. The transparency file must list the same tokens, one per
   line, same order.

8. Digests. For an observation root, `band_digest` is the lowercase hex sha256
   digest of the UTF-8 string formed by joining every channel's bands in sorted
   `sid` order with `,` separators inside a channel and `|` between channels,
   each band formatted with exactly six digits after the decimal point.
   `q_digest` uses the same join rules over `Q` vectors.

Obligation: zero algebra violations on primary corpora and on held-out corpora
after these rules, including after a second driver run that reseeds from the
campaign journal written by the first run.
