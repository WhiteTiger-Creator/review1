# Anisotropic arena replay contract

Implement `/app/environment/src/flux_recon.cpp` as the Anisotropic deterministic replay analyzer for `*.flux` arena cases.

## CLI

Supported options:

- `--case-dir <path>`: directory containing `*.flux` files. Default: `/app/environment/cases`.
- `--out <path>`: JSON report path. Default: `/app/output/flux_report.json`.
- `--max-rounds <N>`: optional positive integer cap. Simulate at most `min(N, rounds)` rounds from each case.

Unknown options, missing option values, invalid cases, or impossible output writes are errors.

## File format

A case file is ASCII text. Before processing any line, trim leading and trailing spaces, tabs, and carriage returns. After this trim, blank lines are ignored and lines beginning with `;` are comments. All tokens are whitespace-separated. Grid row length is checked after this trim, so an indented line such as `        ########` is a valid 8-cell grid row, not a 16-character row.

Required sections, in order:

```text
case_id <id>
rows <R>
cols <C>
rounds <T>
grid
<R rows of exactly C characters>
end_grid
actors
<actor_id> <row> <col> <energy> <priority>
...
end_actors
commands
<actor_id> <cmd_1> <cmd_2> ... <cmd_T>
...
end_commands
```

`id` and `actor_id` must match `[A-Za-z0-9_-]+`. Actor ids are sorted lexicographically whenever an output list or event list needs actor ordering. Rows and columns are zero-based.

Grid characters:

- `#`: wall; actors cannot enter.
- `.`: floor.
- `E`: exit tile.
- `H`: hazard tile.
- `+`: charge tile.
- `P`: pressure plate.
- `G`: locked gate tile.
- `T`: turret tile.
- digits `0` through `9`: portal tiles. Each digit used in a case must appear exactly twice. A digit may be absent.

Actor rows and columns must be in bounds and not on a wall. Two actors may not start on the same cell. Energy must be from `0` to `9`. Priority must be an integer from `0` to `99`; lower numbers win conflicts.

Commands:

- `W`: wait.
- `N`, `S`, `E`, `WST`: one-step north, south, east, west. `WST` is used for west to avoid conflicting with wait.
- `DN`, `DS`, `DE`, `DW`: dash two microsteps in the named direction.

Every actor must have exactly `T` commands. Commands for actors not listed in the actors section are invalid. Actor command rows may appear in any order.

## Round simulation

Only actors with status `active` issue commands. Actors with status `exited` or `down` are ignored in later rounds.

Each round has these phases. Event spellings are exact. In particular, bump events always include the conflict winner id: `r<round>:<actor>:bump:<winner>`.

### 1. Command normalization

If an active actor has command `W`, it proposes to stay and has command cost `0`.

A one-step command has command cost `1` and one microstep. A dash has command cost `2` and two microsteps. If an actor's current energy is less than the command cost, the command becomes wait, the event `r<round>:<actor>:tired` is emitted, and the actor recovers as a wait action in the energy phase.

### 2. Proposal microsteps

Proposals are computed independently from the actor's current position before conflicts are resolved.

For each microstep:

1. Move one cell in the command direction.
2. If the candidate is outside the grid or is `#`, the proposal is blocked at the actor's current starting cell. Emit `r<round>:<actor>:wall` and cancel remaining microsteps.
3. If the candidate is a locked `G` tile and the arena gates are not open, the proposal is blocked at the actor's current starting cell. Emit `r<round>:<actor>:gate` and cancel remaining microsteps. Gates start closed and may open later as described below.
4. If the candidate is in the current echo set, the proposal is blocked at the actor's current starting cell. Emit `r<round>:<actor>:echo` and cancel remaining microsteps.
5. Otherwise the actor reaches the candidate. If the candidate is a portal digit, teleport immediately to the matching portal cell and emit `r<round>:<actor>:portal:<digit>`. Teleport destinations are allowed to be occupied at proposal time; conflicts are resolved later.

The round number in events is zero-based. Echoes are cells vacated by actors that successfully moved in the previous round only. Echoes expire after one round. Echoes do not block actors that choose wait on their current cell; they only block entering a candidate cell during a microstep.

### 3. Simultaneous conflict resolution

Let each active actor have a start cell and a proposed destination.

- Actors proposing their own start cell are stationary.
- If multiple actors propose the same destination, only the winner remains a mover. The winner is the actor with the lowest priority; ties use lexicographic actor id. Every loser is blocked at its start cell, increments `bumps`, and emits `r<round>:<actor>:bump:<winner>`.
- A direct two-actor swap is allowed when two actors uniquely propose each other's start cells. Both move, even though each destination was occupied at the start of the round.
- For all other movers, a move is invalid if its destination is occupied by an actor that is stationary or whose move has already been invalidated. Such a mover is blocked at its start cell, increments `blocks`, and emits `r<round>:<actor>:blocked:<occupant>`.
- Occupancy blocking is iterative: after invalidating a mover, re-check movers that target its start cell until no more invalidations are possible.

When several actors must be invalidated during the same occupancy-blocking pass, process them in lexicographic actor-id order.

### 4. Apply moves, terrain, and arena devices

Accepted movers change to their proposed destination and pay the command cost. Stationary wait actors recover one energy, up to a maximum of `9`. Actors blocked by wall, gate, echo, bump, or occupancy do not pay command cost and do not recover energy.

Then resolve terrain and devices in the following order. Within actor-specific subphases, process actors by lexicographic actor id.

1. Hazard and charge terrain: an active actor on `H` loses one energy and emits `r<round>:<actor>:hazard`; an active actor on `+` gains two energy up to maximum `9` and emits `r<round>:<actor>:charge` only if its energy increased. If energy becomes negative, set status `down` and emit `r<round>:<actor>:down`.
2. Pressure plates: if the gates are currently closed and at least one active actor is on a `P` tile, gates become open permanently and the single event `r<round>:arena:gate_open` is emitted. Open `G` tiles behave like floor for later rounds.
3. Turrets: each active actor with line of sight to a `T` in the four cardinal directions loses two energy and emits `r<round>:<actor>:laser`. Line of sight stops at `#` and at closed `G` gates; open gates do not block line of sight. If energy becomes negative, set status `down` and emit `r<round>:<actor>:down`.
4. Exits: each active actor on an `E` tile with nonnegative energy becomes `exited` and emits `r<round>:<actor>:exit`.

### 5. Next echo set

The next round's echo set is the set of start cells of actors whose moves were accepted and whose destination differs from their start cell. Include actors that exited or went down after the accepted move.

## Scoring

For each actor:

- `+100` if status is `exited`.
- `-40` if status is `down`.
- `+5 * energy` for non-down actors after the final simulated round.
- `-7 * bumps`.
- `-3 * blocks`.

The match score is the sum over actors.

## JSON output

Write compact deterministic JSON with these exact top-level keys in this order:

```json
{"matches":[...],"summary":{...}}
```

Matches are sorted by internal `case_id`. Each match object has exactly these keys in this order:

```json
{
  "case_id":"...",
  "rounds_completed":0,
  "actors":[...],
  "events":[...],
  "score":0,
  "digest":"0000000000000000"
}
```

Actors are sorted by actor id. Each actor object has exactly these keys in this order:

```json
{"id":"A","row":0,"col":0,"energy":0,"status":"active","bumps":0,"blocks":0}
```

`status` is one of `active`, `exited`, `down`.

`events` are emitted in phase order. Within the same phase, use lexicographic actor id order unless a rule above specifies a different order. Keep duplicate event strings if they occur.

The summary object has exactly these keys in this order:

```json
{"match_count":0,"total_score":0,"exited_count":0,"down_count":0,"digest":"0000000000000000"}
```

Do not add extra keys.

## FNV-1a digests

Use 64-bit FNV-1a with:

- offset basis `0xcbf29ce484222325` (`14695981039346656037ULL`)
- prime `0x100000001b3` (`1099511628211ULL`)

Hash raw ASCII bytes of each token string in the listed order. Do not hash JSON. Do not insert separators other than the literal colons shown in tokens.

For each match digest, append:

1. `case:<case_id>`
2. `rounds:<rounds_completed>`
3. For each actor in output order: `actor:<id>:<row>:<col>:<energy>:<status>:<bumps>:<blocks>`
4. For each event in output order: `event:<event>`
5. `score:<score>`

The 16-character lowercase hexadecimal digest of this stream is the match `digest`.

For the summary digest, append:

1. For each match in output order: `match:<case_id>:<digest>:<score>`
2. `counts:<match_count>:<total_score>:<exited_count>:<down_count>`

The 16-character lowercase hexadecimal digest of this stream is the summary `digest`.

## Invalid input and atomic output

On any invalid input or CLI error:

- exit with code `2`,
- delete the requested output file if it already exists,
- write no partial JSON report,
- print a diagnostic to stderr containing `invalid` or `error` after lowercasing.

Invalid conditions include malformed sections, duplicate actor ids, duplicate start cells, actors on walls, illegal grid characters, portal digits appearing other than exactly twice, missing command rows, wrong command counts, unknown commands, and impossible output paths.
