# Tempo-cooldown and root-analysis appendix

This appendix extends the Abalone replay contract and the strategy refinement
appendix. All requirements in those documents still apply unless explicitly
extended here.

## Tempo cooldown

`rules` has one additional integer field, `tempo_cooldown`, from 0 through 3.
The value is the number of that player's future accepted moves for which a
marble selected by an accepted move may not be selected again. Zero disables
the mechanism.

`initial` has an additional `cooldowns` array. Each item has exactly `q`, `r`,
`player`, and `remaining`. Inputs are structurally valid: every listed cell
contains that player's marble, no cell occurs twice, `remaining` is from 1
through `tempo_cooldown`, and the array is empty when `tempo_cooldown` is zero.
A cooldown belongs to the marble at its cell, not permanently to the cell.

In move validation, after the combined `not_owned` check and before the
collinearity check, reject with `marble_cooling_down` if any selected marble
has a cooldown. This check covers the entire selection and has that single
reason. Rejections, including ko rejections, never age cooldowns.

Apply cooldown state provisionally as part of every geometrically legal move:

1. Cooldowns on pushed opponent marbles travel one cell with those marbles. A
   cooldown on an ejected marble disappears.
2. Move the selected marbles normally. A selected marble cannot already have a
   cooldown because of validation.
3. Decrease `remaining` by one on every pre-existing cooldown belonging to the
   mover, wherever that marble is now located, and remove entries that reach
   zero. Do not age the other player's cooldowns.
4. If `tempo_cooldown` is nonzero, put a cooldown with
   `remaining=tempo_cooldown` on every selected marble at its destination.

The cooldown update happens before forming the prospective repetition
fingerprint and before the ko check. Consequently ko compares cooldown state
as well as board and scores. A ko rejection restores every cooldown to its
pre-move cell and remaining value along with all other provisional effects.
An accepted move keeps its cooldown update even if it ends the game.

Cooldown state is part of an active position. Extend the canonical position key
to this exact form:

`next=<next>|score=<player0>:<score0>,<player1>:<score1>|cooldown=<q>,<r>:<player>:<remaining>;...|board=<board-entries>`

Cooldown entries are sorted by ascending numeric `q`, then ascending numeric
`r`, and have no trailing semicolon. The section is empty when no marble is
cooling down. For rotational and dihedral repetition equivalence, transform
cooldown coordinates together with their marbles before serializing each
candidate; player ids and remaining values do not change. The reported
physical position key is never transformed.

Legal-action enumeration and every continuation branch carry complete cooldown
state. A candidate selecting a cooling marble is illegal. This may cause an
otherwise occupied ongoing position to become a `stalled` leaf.

Extend `final` by inserting `cooldowns` after `ejections`. It is the sorted
array of cooldown objects in the same order and exact shape as
`initial.cooldowns`, including an empty array when none remain. Thus `final`
has exactly `status`, `winner`, `legal_moves`, `no_progress`, `ejections`,
`cooldowns`, `next_player`, `position_key`, and `board`.

## Root-action analyses

The continuation proof must expose the independently computed proof below
every root action. Extend `continuation` by inserting `root_analyses` after
`root_action_count`. It is empty when the root is a leaf or has no legal
actions. Otherwise it contains one object per canonical root action, in
canonical action order, with exactly:

- `action`: that root action key.
- `nodes`: the child proof's node count, including the child.
- `leaves`: the child proof's leaf count.
- `leaf_counts`: the child proof's seven-key leaf-count object.
- `utility`: the complete propagated child utility.
- `principal_variation`: the child proof's principal variation; it does not
  repeat `action`.
- `digest`: the child proof's recursive digest.

These values describe the child at remaining depth
`continuation_depth - 1`. The root's own `nodes`, `leaves`, `leaf_counts`,
utility, optimal actions, principal variation, and digest are unchanged and
must agree with the analyses. In particular, root `nodes` is one plus the sum
of analysis `nodes`, root `leaves` and each leaf-count component are the sums
of the corresponding analysis values, and a branch root principal variation
starts with its selected root action followed by that analysis's variation.

Consequently `continuation` has exactly `depth`, `root_action_count`,
`root_analyses`, `nodes`, `leaves`, `leaf_counts`, `value`, `utility`,
`optimal_actions`, `principal_variation`, and `digest`.

## Momentum economy

`rules` has one additional integer field, `momentum_cap`, from 0 through 6.
Zero disables momentum. `initial` has a `momentum` object containing exactly
the two player-id keys. Each value is from zero through `momentum_cap`, and
both values are zero when momentum is disabled.

Momentum changes push legality and is part of the active position. Apply the
ordinary geometric movement checks first, including `insufficient_force` and
`blocked`. If the geometrically legal move would push `N` opponent marbles
and the mover has less than `N` momentum, reject it with
`insufficient_momentum`. This check occurs after every geometric rejection
reason and before any provisional state update.

For a provisionally accepted move:

- a move that pushes no marbles adds the selected group size to the mover's
  momentum, capped at `momentum_cap`;
- a move that pushes `N` marbles subtracts exactly `N` momentum from the
  mover, including when it ejects the final opponent marble; and
- the other player's momentum never changes.

Perform this update together with board, score, and cooldown updates before
forming the prospective repetition fingerprint. A ko rejection restores both
players' momentum exactly. Other rejections never change momentum.

Insert a momentum section into the canonical position key:

`next=<next>|score=<player0>:<score0>,<player1>:<score1>|momentum=<player0>:<value0>,<player1>:<value1>|cooldown=<cooldowns>|board=<board-entries>`

Player order is always `players` order. Momentum is invariant under rotations
and reflections, but it remains in every symmetry candidate. Therefore two
otherwise symmetric positions with different momentum are not equivalent.

Every result adds `momentum` immediately after `ejected`. It is a fresh object
containing both current values after that result, including after a rejection.
Insert the same object in `final` immediately after `ejections`. Legal-action
enumeration and every continuation occurrence carry momentum and reject
unaffordable pushes.

## Tactical quiescence extension

`rules` has one additional integer field, `quiescence_depth`, from 0 through
2. It extends tactical push sequences after the ordinary
`continuation_depth` horizon without changing replay adjudication or the
per-result legal-action census.

At positive ordinary remaining depth, expand every canonical legal action as
before and decrement ordinary depth. Once ordinary remaining depth is zero:

1. If quiescence remaining is zero, classify the node as `horizon`.
2. Otherwise enumerate legal actions and retain only tactical actions. A
   tactical action is one whose accepted move pushes at least one opponent
   marble, whether or not it ejects.
3. If no tactical action exists, classify the node as `horizon`.
4. Otherwise expand every retained action in canonical order, keep ordinary
   remaining depth at zero, and decrement quiescence remaining.

An ended state is always its ordinary ending leaf before either depth check.
An ongoing state is `stalled` only at positive ordinary depth when it has no
legal actions. At ordinary depth zero, lack of tactical actions is `horizon`.
Every retained tactical branch is still an independent occurrence and carries
complete board, cooldown, momentum, counter, history, and occurrence state.

Add `quiescence_depth` after `depth` in `continuation`. Add
`quiescence_nodes` after `nodes` in both `continuation` and every
`root_analyses` item. `quiescence_nodes` counts nodes reached by following at
least one tactical extension edge; the nominal-horizon node itself is not
counted until such an edge is followed. Parent values are the sums of child
values. It is zero when no extension edge is traversed.

The recursive digest now commits both remaining depths. Its exact UTF-8
preimages replace the earlier forms with:

```text
L\n<remaining>\nquiescence=<quiescence-remaining>\n<leaf-kind>\n<position-key>\nlegal=<legal_moves>\nno_progress=<no_progress>
N\n<remaining>\nquiescence=<quiescence-remaining>\n<position-key>\nlegal=<legal_moves>\nno_progress=<no_progress>\n<action-key> <child-digest>\n...
```

There is still no trailing newline. A quiescence branch contains only retained
tactical children.

When the proof root itself is at ordinary depth zero and extends tactically,
`root_analyses` contains only those retained tactical children, while
`root_action_count` still reports the complete legal-action count. With no
retained tactical child the root is a horizon leaf and `root_analyses` is
empty.

Extend utility to `(outcome, margin, momentum, tempo)`. `momentum` is player
0's momentum minus player 1's momentum at the leaf. Compare it after `margin`
and before `tempo`; all other utility propagation and player min/max behavior
is unchanged. Add the integer `momentum` field between `margin` and `tempo` in
every reported utility object.

After all extensions, `continuation` has exactly `depth`,
`quiescence_depth`, `root_action_count`, `root_analyses`, `nodes`,
`quiescence_nodes`, `leaves`, `leaf_counts`, `value`, `utility`,
`optimal_actions`, `principal_variation`, and `digest`. Each root analysis has
exactly `action`, `nodes`, `quiescence_nodes`, `leaves`, `leaf_counts`,
`utility`, `principal_variation`, and `digest`.
