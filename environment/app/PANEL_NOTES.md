# Contract index (read every file)

The operations contract is split so each file stays short enough to read in full.
All files under `/app/contract/` are normative. Skip none.

| File | Contents |
|------|----------|
| `/app/contract/01_invoke.md` | make target, OUT scrub/hygiene, exits, notes |
| `/app/contract/02_catalog.md` | clock, lamps, blackouts, operators |
| `/app/contract/03_alarms.md` | flaps, collapse, primary span age, ack grace gate |
| `/app/contract/04_routes_bells.md` | handoff-ranked runners, hop_waiver, local-only depth tax |
| `/app/contract/05_render.md` | widths, pre-silence width, local CLEAR silence, taxes |

Panel table headers in `/app/panel/*.tsv` match these docs. Implement in Perl under
`/app/lamps` only.
