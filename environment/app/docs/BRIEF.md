# Sedgemere: reading the levels

The beck at sedgemere is surveyed one spot at a time. A surveyor takes eight
readings and the water level at that spot is written down afterwards. We have
four thousand past surveys with their levels, and we need a book that can give
the level for a spot from its readings alone.

## The readings

| column | |
| --- | --- |
| `reed`, `silt`, `brack`, `fen` | continuous readings, roughly standard normal |
| `moss`, `gale` | two more continuous readings |
| `sluice`, `weir` | gates, open or shut, written 0 or 1 |

Not every reading carries anything.

## The data

`/app/data/train.csv` holds four thousand surveys: the eight readings and then
`level`, the level that spot turned out to hold.

`/app/data/dev.csv` holds eight thousand more surveys without their levels, and
`/app/data/dev.levels` holds those levels, one to a line, in the same order, so
you can measure yourself honestly before you are measured.

## What the levels do

Three things are worth knowing before you spend the budget, and none of them
is the answer.

The first is that weighing each reading on its own and adding the weights up
stalls a long way short, and so does a tree ensemble handed the readings
exactly as they arrive. Two of the readings carry almost nothing apart and a
great deal together, and no weight on either alone can stand in for that.

The second is that **which readings those are is not the same for every
survey**: one of the gates decides it, so a combination that carries the
levels where that gate is open carries nothing where it is shut. Looking for
one combination across all four thousand surveys at once will find neither of
them. Nor is every reading's pull a straight line in it.

The third is about the levels rather than the readings. A level is usually
read to within a hand's breadth, but roughly one survey in six is a spike,
and **a spike is always upward, never downward.** What that does to a fit, and
what it means for a book scored on the plain size of its misses, is yours to
work out.

## What you must build

The book lives under `/app/src` as C++ sources. Every `.cpp` file there is
compiled together with `g++ -O2 -std=c++17`, and the `main` must be among
them. It is run as

    sedgemere <readings file> <levels file>

reading a CSV with the same header and columns as `dev.csv` and writing one
level per survey, in the order it received them, one to a line, as a plain
decimal number. It may read `/app/data/train.csv` while it runs. Nothing
beyond the C++ standard library is available and there is no network. One run
must finish within five minutes.

## How you are scored

The book is handed surveys drawn fresh from the same beck, whose levels it has
never seen, and scored on the average distance between the level it gives and
the level held. It must come within **1.35** on each of several fresh draws.
Giving every spot the middle of the training levels misses by about 2.8, and
the best a book could do is about 1.25, because the spikes are not predictable
from the readings.
