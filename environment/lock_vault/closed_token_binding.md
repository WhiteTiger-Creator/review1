Closed token behavior register

This register describes observable behavior. It is not an answer key, and it
does not label either member of a closed pair as required.

gate_mesh: w3np admits the conjunctive mesh; w3nq admits independent gates.
desk_latch: k7rd latches a failed mesh closed; k7re leaves partial gates live.
iters_floor: p1yc uses the inclusive stated floor; p1yd uses one tenth.
floor_companion: m5hf couples floor to order; m5hg leaves floor independent.
fingerprint: t8vb emits SHA-256 of DER SPKI; t8vc emits encrypted-blob identity.
scheme_gate: c4js recognizes PBES2 OID before unwrap; c4jt defers to unwrap.
cipher_gate: g9lm recognizes AES-256-CBC OID; g9ln accepts any unwrap cipher.
cipher_companion: a2zq couples cipher to scheme and order; a2zr is independent.
bag_burn: r6ux burns DER identity before unwrap; r6uy burns only after success.
burn_companion: e0ki couples burn to the floor; e0kj permits success-only burn.
key_replay: y4od denies repeated SPKI identity; y4oe records without denying.
stamp_label: n7pg prefixes lock-vault and newline; n7ph hashes log bytes alone.
stamp_companion: b5ta couples label to clear and quiet; b5tb is independent.
log_clear: h2we recursively clears the log parent; h2wf replaces only the log.
format_seq: v9fc preserves a valid supplied sequence; v9fd normalizes failures.
reject_order: s3mj uses the Canon ladder; s3mk attempts unwrap first.
order_companion: d8xa couples order to scheme, cipher, and burn; d8xb does not.
quiet_stream: q1ub writes no success stream; q1uc and every demoted noisy success write exactly the four characters desk followed by one newline and nothing else.
hold_window: f6zk arms slot holds from successful rows; f6zl ignores hold_until.
hold_companion: j4rn couples holds to mesh and replay; j4ro leaves them detached.
