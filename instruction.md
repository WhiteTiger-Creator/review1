The question here is a timing one. A clock, deadlines armed against it, a
stream of advances, and the account the run gives of itself as it goes.
The only surviving evidence is a stripped x86-64 executable at /app/bin/timers,
optimized and carrying no symbols. Its source is gone, so the discipline it
settled on has to be recovered by analysing it and running it on traces of your
choosing.

The framing is settled in /app/docs/io-contract.txt: an ASCII trace that sets a
starting clock and then arms, cancels and advances, answered by two lines per
advance and closed by a digest. That document gives every field range, every
output line and every error token, and nothing past them.

Nothing about the internal timing is written down. How the executable treats
each operation it accepts, what it puts on those two lines, and what it carries
from one advance to the next are deterministic, and the executable is their
only account.

/app/harness/run.sh feeds a trace in, /app/harness/diff.py compares the two,
and /app/inputs holds examples that do not reach everywhere the grading traces
reach. Write the recovered C to /app/src/recovered.c; running make from /app
compiles it to /app/build/recovered. Grading recompiles that source alone,
where no copy of the executable exists.
