Our fleet controller rolls out canary batches by tagging m consecutive
server slots 1 through m, left to right, each time it runs a rotate
command. A later rotate overwrites whatever tag an earlier one left on any
slot it also covers. By the time a window closes, every slot in scope has
to have been tagged at least once, otherwise it silently kept running the
pre-rollout build.

The audit exporter that streams these tags out had a race condition during
last night's incident, so a chunk of what it recorded almost certainly
doesn't match anything the controller could have actually produced, and we
need it cleaned up before it goes into the incident report.

`rotctl` is the on-call repair tool for this. The CLI and I/O plumbing are
already wired up in `/app/src/main.rs`; what's missing is the repair logic
in `/app/src/repair.rs`. For each recorded window, it needs to report the
fewest tags that must have been corrupted, and hand back a corrected tag
array that some legitimate rotate history really could have produced.
`/app/docs/rotation-contract.md` has the exact input and output format
`main.rs` expects.

A single report can bundle up to 10000 windows totaling half a million
slots, and on-call doesn't have all night — this needs to come back in a
couple of seconds, nothing that scales with trying out every correction.

If time gets tight, get a correct `rotctl repair` running end to end on
smaller windows first and tighten it for the half-million-slot case after —
a slower pass that's actually wired up beats a faster design that never
made it into `repair.rs`.
