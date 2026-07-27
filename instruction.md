# World Bank Country Tracker

Build a small economic-data analysis pipeline that ingests World Bank
country indicators, keeps a tamper-evident record of every change, and
answers rigorous statistical questions about the dataset — inequality
across regions, how a country's standing shifts as new data arrives, and
whether the historical record has been altered.

Country records are pulled from the World Bank open-data source and stored
in a local SQLite database, with the exact schema, request shape, and error
behavior spelled out in the referenced docs rather than here. Every insert
also appends an entry to a running, cryptographically-chained audit log —
each entry binds a snapshot of the distribution's shape at that moment
(its center, spread, and higher moments), so the log doubles as an
integrity trail over the statistics themselves, not just the raw records.
Two commands can replay that chain in either direction to catch any
tampering; the exact preimage format and byte order matter and are covered
in the HMAC and chain-format references.

On the analysis side, the tool reports the standard descriptive measures,
several inequality and concentration indices, and a handful of
regression/correlation measures — all using population-level statistics,
consistent rounding, and the log bases and edge-case handling called out in
the statistics references. One report goes further: a country's standing
relative to its own region is recomputed live from the current table every
time it's asked for, rather than cached from when the country was first
seen, so a region's membership picture can shift as new entries arrive. A
separate audit-side report tracks which log entries currently belong to a
bounded "trusted" reference window, aging entries out on a delay tied to
when they actually joined that window rather than when they were first
recorded.

See `/docs/operations-reference.md` for the full command reference, sample
runs, and edge-case notes — read it before implementing, since exact
formulas, field orders, and precision rules live there rather than being
repeated inline. The record source is mocked, so no network access is
needed at runtime. Grading inspects the populated database tables and the
run report written under the output directory.
