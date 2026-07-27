Ship contract (hostctl-export systemd oneshot)
==============================================

Unit and mounts
---------------
``/app/svcunit/metricd.service`` is a Type=oneshot RemainAfterExit unit.
``RequiresMountsFor`` covers the bind-mounted snap trees, exclbook ledgers,
and language packs inventoried in ``/app/svcunit/bind-mounts.conf``.
``/app/scripts/run_ship.sh --from-unit`` applies every ``Environment=`` line
from the unit before ExecStart (site language pack for the ship path).

Entrypoint
----------
``/app/scripts/run_ship.sh`` builds ``/app/bin/metricd`` via
``make -C /app/environment PREFIX=/app install`` and runs the oneshot ship.

Flags: ``--book``, ``--snaps``, ``--out``, ``--langpack``, ``--from-unit``,
``--fresh`` (clears journal, digest, and trace before ship).

Property check: ``/app/bin/check_bin --pack <label>`` where ``<label>`` is
``C`` or ``de_DE``. The flag sets an explicit pack on the case bundle; without
it the tool falls back to the process environment.

Canonical metric text
---------------------
For each selected ``metrics.json`` row (string ``k``, numeric ``v``), emit one
line ``k=<number>`` with exactly six digits after an ASCII period, no thousands
separators, no scientific notation. Sort lines by ``k`` ascending. Hash the
UTF-8 bytes with ``sha256sum``. Write the lowercase hex digest to
``/app/output/canonical_export.sha256``. Language packs and unit
``Environment=`` locale settings must not change those digest bytes.

Snap selection
--------------
Only on-disk snap ids under the snaps root compete. Prefer highest
``evidence_tier`` from the exclbook. On a tier tie, keep supersede-chain roots
only (an id is a root when no other same-tier candidate reaches it through
``supersedes`` edges, directly or through a chain). If more than one root
remains, take the lexicographically minimum id. Bind-mounted tree mtime must
not override that policy.

Journal and recovery
--------------------
Each ship writes ``/app/output/ship_journal.json`` with ``selected_id``,
``book_stamp`` (sha256 of the active book file bytes), ``pack_label``
(``C`` or ``de_DE``), ``stage_path``, ``complete``, and ``generation``.
Metric text is staged under ``/app/output/stage/`` before promote. An
incomplete journal must discard any leftover staged body and re-run selection
plus emit for the active book. A completed journal whose ``book_stamp`` does
not match the active book, or whose ``pack_label`` does not match the active
language pack, is stale and must also re-run. ``generation`` increases on every
re-select or re-emit. Never promote a staged body whose book stamp or locale
encoding disagrees with the active ship.

Trace and case archive
----------------------
Append ``/app/output/reconcile_trace.jsonl`` (do not truncate prior lines).
The final line is a JSON object with ``event`` equal to ``ship_complete``,
``selected_id``, non-empty ``note_text``, ``sha_prefix`` (first 12 hex
characters of that run's digest), and ``pack_label`` of ``C`` or ``de_DE``
matching the active pack. ``/app/bin/check_bin --pack <label>`` writes
``/app/output/counterexample_archive/manifest.json`` with a non-empty
``cases`` array; each case carries non-empty ``case_id``, ``selected_id``,
``note_text``, ``sha_prefix``, and ``pack_label`` aligned with the latest
digest and trace (case ``note_text`` equals or is a substring of the matching
trace ``note_text``).
