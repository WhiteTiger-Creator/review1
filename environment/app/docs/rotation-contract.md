# rotctl repair — I/O contract

`rotctl repair` reads one incident report from stdin and writes the repaired
windows to stdout in the same order. `main.rs` already implements this
framing; `repair.rs` owns only the per-window computation.

## Rotate commands

A rotate command targets a window of `n` slots and a fixed batch size `m`.
It picks a starting slot `l` (`1 <= l <= n - m + 1`) and tags slots
`l, l+1, ..., l+m-1` with `1, 2, ..., m` in order. If a later rotate command
also covers a slot, its tag replaces whatever tag that slot already had. A
window's recorded tag array is "producible" if some sequence of rotate
commands exists that covers every slot in the window at least once and
results in exactly that array.

## Input format

```
T
n_1 m_1
tag_1_1 tag_1_2 ... tag_1_n1
n_2 m_2
tag_2_1 tag_2_2 ... tag_2_n2
...
```

- `T` — number of windows in this report, `1 <= T <= 10000`.
- Each window: `n` (slot count) and `m` (batch size), `1 <= m <= n`, then `n`
  tags, each an integer in `[1, m]`.
- The sum of `n` across every window in one report is at most `500000`.

## Output format

For each window, in the same order as the input, two lines:

```
R
corrected_1 corrected_2 ... corrected_n
```

- `R` — the minimum number of tags in this window that must be corrected.
- The corrected tag array: length `n`, values in `[1, m]`, differing from
  the recorded window in exactly `R` positions, and itself producible per
  the definition above.

## Example

Input window `n=4 m=3`, tags `1 2 2 3` is not producible as recorded (no
rotate history explains it), and the minimum repair is one tag: `R=1` with
corrected tags `1 2 3 3`.
