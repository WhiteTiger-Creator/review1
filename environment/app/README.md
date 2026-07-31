# Gauntlet

You are given data about a contest and must implement one function.

## Files

- `logs.json`  -  110 recorded bouts. Each entry is `{ "name", "left", "right", "winner" }`, where
  `winner` is either `"left"` or `"right"`. Nothing about how the Warden reached that verdict is
  written down.
- `cases.json`  -  15 practice rounds of the form `{ "name", "mine", "rivals" }`, with no outcome
  given. Use them to try out your strategy.
- `strategy.js`  -  the module you edit. It must export `chooseChampion(round)`.
- `run.js`  -  prints your `chooseChampion()` output for every practice round (`node run.js`).

## Data shapes

A contender is `{ "power": <1..9>, "guile": <1..9>, "armour": <1..6> }`. A round is
`{ "mine": [contender x6], "rivals": [contender x6] }`. Your `chooseChampion(round)` must return an
integer index into `mine`. That contender then fights each of the six rivals in turn, and the round
is judged on how many of those six bouts it wins.

## Notes

Every contender in a round is described by the same three traits, and the Warden applies the
same rule to every bout, whichever round it comes from.

Sizes and traits are integers, and every bout in the log was settled by the same rule.
