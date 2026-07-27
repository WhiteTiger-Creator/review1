An air-hockey rally does not wait for a nominal tick to finish before several impacts occur. Complete the Java 17 rollback simulation under /app/src and run make -C /app install to produce /app/lib/glideclash.jar. No task executable or result file is permitted; verifiers call only the public API on that jar.

Read and implement /app/tablebook/rollback-contact.api as the authoritative contract. Every enum value, record field, Engine method, exception code, validation precedence rule, input receipt, physics formula, and event id convention in that file is required. The stubs under /app/src and examples under /app/examples must satisfy that contract after install.

Public Engine surface:
- Engine.start(Blueprint), headTick(), snapshot(), submit(InputFrame), advanceTo(long), fork()
- InputStatus: STORED, REVISED, IDEMPOTENT, STALE_SEQUENCE, TOO_OLD, CONFLICT, UNKNOWN_PLAYER, INVALID_INPUT
- EventKind: GOAL, WALL, GATE, BUMPER, PADDLE, PUCK
- Snapshot: headTick, leftScore, rightScore, pucks, paddles, pendingServes, actions
- BodyView: id, x, y, vx, vy, xRemainder, yRemainder
- ArenaEvent: tick, subframe, kind, primaryId, secondaryId
- GlideFrame: tick, corrected, snapshot, events
- PhysicsException codes: arithmetic, impact-limit, ricochet-cap

Blueprint validation is order-independent and finishes before Engine allocation. Exception code precedence is exactly: rules, duplicate-id, player, bounds, home, goal, gate, overlap, null-member. Within one code, the lexically smallest offending id wins (or "-" when there is no member id).

Inputs: one effective action per player per tick. Missing authority predicts the prior effective action (initial NEUTRAL). Same player+tick: identical -> IDEMPOTENT; lower sequence -> STALE_SEQUENCE; equal sequence with different action -> CONFLICT; higher sequence replaces. Invalid/stale/conflict/too-old leave state unchanged. Future/current accepted -> STORED. Past inside the rollback window -> REVISED (restore that tick, keep later authority, resimulate to the former head); past outside -> TOO_OLD. Corrections contain only structurally changed frames, each with corrected=true, sorted by tick. A paddle action for a tick is authoritative only when that player+tick has a stored InputFrame; otherwise it is predicted (this changes paddle impulse below).

Event ids (tests assert these strings exactly):
- GOAL: primaryId=puck id, secondaryId=goal id. LEFT mouth scores for RIGHT (rightScore++) and queues PendingServe(puck, LEFT); RIGHT mouth scores for LEFT. Goal suppresses WALL for that puck in the same subframe.
- WALL: primaryId=puck id, secondaryId exactly left|right|top|bottom (never "-").
- GATE/BUMPER/PADDLE: primaryId=puck id, secondaryId=fixture id.
- PUCK: primaryId=lexical-smaller puck id, secondaryId=lexical-larger puck id.
Sort events by subframe, kind order GOAL,WALL,GATE,BUMPER,PADDLE,PUCK, then primaryId, then secondaryId.

Physics uses signed long with addExact/subtractExact/multiplyExact (no floating point). Per axis each subframe: remainder += velocity; delta = floorDiv(remainder, subframes); remainder = floorMod(...); pos += delta. Tick order: respawn pending serves; choose actions; for each subframe move paddles (home-clamp zeroes clamped-axis remainder), move pucks, resolve boundaries, then contact islands (at most four sweeps; unresolved approaching overlap throws impact-limit and rolls the entire advanceTo back).

Boundaries per puck per subframe: goals before walls; walls purge the bounced-axis remainder to 0 when reflecting; gates negate the gate-axis velocity, purge that axis remainder, then immediately re-check walls for that puck. Serve at the next tick start, center of rink, vy=0, remainders 0, directed AWAY from the exited mouth (LEFT exit => vx=+serveSpeed; RIGHT exit => vx=-serveSpeed).

Contacts: axis X when |dx|>=|dy| else Y; coincident centers force X with the lexical-smaller id on the negative side. Separate always; velocity response only when approaching. PUCK swaps contact-axis velocities. BUMPER (after separate): outwardSign from puck-minus-bumper on the axis (orientation if zero); tick-global bumperResponseOrdinal starts at 0 each tick and increments on each bumper velocity response; effectiveKick = floorDiv(kick, ordinal); v = clampSpeed(-(v) + outwardSign * effectiveKick, maxSpeed). PADDLE (after separate): authoritative => clampSpeed(2*pad_v - puck_v, maxSpeed); predicted => clampSpeed(pad_v - puck_v, maxSpeed); orthogonal component unchanged. Each emitted WALL/GATE/BUMPER/PADDLE increments that puck's ricochetCount; if it exceeds floorDiv(subframes, 2), throw ricochet-cap and roll back the advance. PUCK events do not count toward the cap.

Never use threads, randomness, clocks, locale data, or filesystem access. Equivalent blueprint list order and advance chunking must yield equal frames; invalid blueprints and conflicting inputs must leave the engine unchanged; mutable caller collections or one Engine instance must not contaminate another.
