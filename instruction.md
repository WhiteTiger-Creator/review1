The question here is a timing one. Given a clock, a set of deadlines armed
against it, and a stream of advances, which deadlines come due at which tick,
and in what order are they reported when several come due during one advance.
The only surviving evidence is a stripped x86-64 executable at /app/bin/timers,
optimized and carrying no symbols. Its source is gone, so the discipline it
settled on has to be recovered by analysing it and running it on traces of your
choosing.

The framing is settled in /app/docs/io-contract.txt: an ASCII trace that sets a
starting clock and then arms, cancels and advances, answered by one due line
and one live count per advance and closed by a digest. That document gives
every field range, every output line, and every error token.

Nothing about the internal timing is written down. How the executable treats
each operation it accepts, and how it decides which deadlines come due and in
what order, are deterministic, and the executable is their only account.

/app/harness/run.sh feeds a trace in, /app/harness/diff.py compares the two,
and /app/inputs holds examples that do not reach everywhere the grading traces
reach. Write the recovered C to /app/src/recovered.c; running make from /app
compiles it to /app/build/recovered. Grading recompiles that source alone,
where no copy of the executable exists.
