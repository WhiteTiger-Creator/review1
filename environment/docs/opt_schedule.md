Optional-dependency activation schedule

Rows in docs/mx_rows.yaml list gem_id, platform, priority, opt_class (gate or side), and overlay_ref.

Default ordering (gate-first)

1. ascending priority
2. gate before side when priorities tie
3. ascending gem_id as final tie-break

--sides-first

Step 2 reverses (side before gate). Priority and gem_id ties stay as above.

act_ord is the zero-based index in that order. opt_side copies opt_class.

Priority ties are meaningful. Equal-priority gate/side pairs reverse under --sides-first while the default gate-first schedule stays stable. Do not sort by gem_id alone, and do not drop the gate/side key when priorities are unique on a training glance.
