# Floating-point tolerance and reproducibility (tol_n)

1. Band comparisons use absolute epsilon `1e-9`. Two bands match when
   `abs(a - b) <= 1e-9`.

2. Budget comparisons use absolute epsilon `1e-9` on each `Q[i]`.

3. Digests are lowercase hexadecimal sha256 strings (`python3
   /app/environment/tools/sha256_hex.py` prints the same digest for a file).
   Matching is exact string equality after regeneration.

4. Driver determinism: two successive runs of `/app/environment/drive_k4.sh`
   with the same corpora must produce byte-identical
   `/app/output/obs_primary.json`, `/app/output/obs_hold.json`,
   `/app/output/rights_map.json`, and `/app/output/transparency.txt`.

5. JSON artifacts use compact encoding with object keys sorted lexicographically
   at every object level. Floating values in JSON use Go `encoding/json`
   default formatting for `float64`.
