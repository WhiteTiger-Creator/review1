# AC grid physics

Stable labels `POWER-01` through `POWER-12` define the network deck, bus and branch semantics, admittance assembly, injections, state layout, mismatches, base-point qualification, terminal flows, canonical identity, the admittance companion, and model failures.

## Operator contract (commands, diagnostics, and companion JSON)

Public executable: `/loadcrest/bin/fold-map`.

```text
/loadcrest/bin/fold-map admittance --network /absolute/network.acn
/loadcrest/bin/fold-map trace --network /absolute/network.acn --ramp /absolute/loading.rmp --map /absolute/result.vcm
```

`admittance` validates POWER-01 through POWER-04 and writes one canonical JSON document to stdout (POWER-11). `trace` performs the scored continuation and publishes the voltage-collapse map described in `continuation-map.md` (TRACE-12 / TRACE-13).

Scientific failures write exactly one JSON line to stderr with members `code` and `message`, write nothing successful to stdout, remove private map material, and preserve any existing `.vcm` byte-for-byte. Stable `code` values (POWER-12):

```text
E_PATH
E_NETWORK_DECK
E_ISLAND
E_BASEPOINT
E_BASE_REACTIVE_LIMIT
E_CONTINUATION
E_REACTIVE_EVENT
E_FOLD
E_MAP
```

## POWER-01 — network deck

The network deck is strict UTF-8 line-oriented text:

```text
AC_NETWORK 1
BASE_MVA <positive>
BUS <id> <SLACK|PV|PQ> <v_set> <angle_deg> <p_gen> <q_gen> <q_min> <q_max> <p_load> <q_load> <g_shunt> <b_shunt>
BRANCH <id> <from> <to> <IN|OUT> <r> <x> <b_total> <tap> <shift_deg>
END
```

Blank lines and lines whose first nonblank character is `#` are ignored. Tokens are separated by ASCII spaces or tabs. Quoting and continuation are forbidden.

After the header, records may appear in any order before `END`.

Exactly one positive finite `BASE_MVA` is required. There are 2–30 buses and 1–60 branches.

Identifiers contain 1–48 ASCII letters, digits, dots, underscores, or hyphens and begin with a letter or digit.

Reject unknown records, trailing tokens, duplicate identifiers, malformed numbers, non-finite values, data after `END`, and missing `END`.

## POWER-02 — bus semantics

Exactly one bus is `SLACK`. Its voltage magnitude and angle are fixed.

A `PV` bus fixes active generation and voltage magnitude while reactive generation is solved inside `[q_min, q_max]`.

A `PQ` bus fixes both active and reactive generation. Its `q_min` and `q_max` fields must both equal its fixed `q_gen`.

Every bus requires:

```text
v_set > 0
q_min <= q_gen <= q_max
p_load >= 0
q_load >= 0
```

All powers are in per unit on `BASE_MVA`. Shunt conductance and susceptance are per unit at `1.0` voltage.

## POWER-03 — branch semantics

For every branch:

```text
r >= 0
x != 0
b_total finite
tap > 0
```

Self-loops are invalid.

`OUT` branches are retained in scientific identity and output inventory but contribute nothing to admittance, connectivity, flow, or continuation.

`IN` branches define the energized topology.

Exactly one energized connected component must contain all buses and the slack bus. Otherwise reject with `E_ISLAND`.

## POWER-04 — complex tap and admittance

For an in-service branch, define:

```text
y = 1 / (r + j*x)
a = tap * exp(j*shift_rad)
y_sh = j*b_total/2
```

With the tap on the declared `from` side:

```text
Y_ff = (y + y_sh) / |a|^2
Y_ft = -y / conjugate(a)
Y_tf = -y / a
Y_tt = y + y_sh
```

Add bus shunts `g_shunt + j*b_shunt` to diagonal entries.

Angles are converted from degrees to radians before trigonometric use.

## POWER-05 — power injections

For bus `i`:

```text
P_i(V,theta) =
  V_i * sum_j V_j *
  (G_ij*cos(theta_i-theta_j)
   + B_ij*sin(theta_i-theta_j))

Q_i(V,theta) =
  V_i * sum_j V_j *
  (G_ij*sin(theta_i-theta_j)
   - B_ij*cos(theta_i-theta_j))
```

These are net injections into the network.

At loading parameter `lambda`:

```text
P_load_i(lambda) = p_load_i + lambda * delta_p_i
Q_load_i(lambda) = q_load_i + lambda * delta_q_i
```

Specified net injection is generation minus load.

## POWER-06 — state variables

The slack angle and magnitude are never state variables.

Every non-slack angle is a state variable.

Every PQ magnitude is a state variable.

A PV magnitude is fixed until a reactive-limit event converts that bus permanently to PQ; its magnitude then enters the state vector.

State order is canonical bus identifier order, first all active angles and then all active PQ magnitudes.

## POWER-07 — mismatch equations

For each non-slack bus, enforce active-power mismatch:

```text
specified_P_i(lambda) - P_i(V,theta) = 0
```

For each PQ bus, enforce reactive-power mismatch:

```text
specified_Q_i(lambda) - Q_i(V,theta) = 0
```

For an unswitched PV bus, computed generation is:

```text
Q_gen_i = Q_i(V,theta) + Q_load_i(lambda)
```

Use an analytic Jacobian consistent with POWER-05 and current bus types.

## POWER-08 — base point

Solve `lambda = 0` before continuation.

The base point must satisfy:

- positive finite voltage magnitudes;
- every absolute power mismatch `<= power_tolerance`;
- every PV reactive generation inside its limits within `reactive_event_tolerance`;
- iteration count within `base_max_iterations`.

A PV bus materially outside a reactive limit at the base point is `E_BASE_REACTIVE_LIMIT`. Do not switch it at zero loading.

## POWER-09 — branch terminal flows

For the critical point, compute:

```text
I_from = Y_ff*V_from_complex + Y_ft*V_to_complex
I_to   = Y_tf*V_from_complex + Y_tt*V_to_complex

S_from = V_from_complex * conjugate(I_from)
S_to   = V_to_complex * conjugate(I_to)
```

Report `P_from`, `Q_from`, `P_to`, and `Q_to` in per unit.

Branch active and reactive losses are the sums of terminal powers.

Out-of-service branches report zero terminal powers and zero losses.

## POWER-10 — canonical network identity

Canonicalize buses by identifier and branches by identifier.

`network_sha256` is lowercase SHA-256 over the canonical line deck using one ASCII space between fields, shortest round-trip finite `float64` formatting, LF endings, and one final newline.

Equivalent record ordering and insignificant whitespace produce the same digest.

## POWER-11 — admittance companion

The complete `admittance` command validates POWER-01 through POWER-04 and emits canonical JSON to stdout with two-space indentation and this fixed top-level member set:

```json
{
  "format": "admittance-companion-v1",
  "network_sha256": "lowercase-hex",
  "base_mva": 0.0,
  "bus_count": 0,
  "branch_count": 0,
  "in_service_branch_count": 0,
  "slack_bus": "id",
  "nonzero_ybus_entries": 0,
  "ybus": [{"row": "id", "col": "id", "g": 0.0, "b": 0.0}],
  "branch_primitives": [{
    "id": "id",
    "from": "id",
    "to": "id",
    "status": "IN",
    "g_ff": 0.0, "b_ff": 0.0,
    "g_ft": 0.0, "b_ft": 0.0,
    "g_tf": 0.0, "b_tf": 0.0,
    "g_tt": 0.0, "b_tt": 0.0
  }]
}
```

Y-bus rows are sorted by `(row, col)`. Branch primitive rows are sorted by branch identifier. Out-of-service branches appear with zero primitive admittances.

It performs no base power flow, continuation, reactive-limit event, fold search, or result-map creation.

## POWER-12 — model failures

Stable scientific failures include:

- `E_PATH`
- `E_NETWORK_DECK`
- `E_ISLAND`
- `E_BASEPOINT`
- `E_BASE_REACTIVE_LIMIT`
- `E_CONTINUATION`
- `E_REACTIVE_EVENT`
- `E_FOLD`
- `E_MAP`

A failure writes one canonical JSON diagnostic line to stderr, no success line to stdout, removes private map material, and preserves any existing map byte-for-byte.
