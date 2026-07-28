# Peer credential bind-cookie model



Operators authorize Unix-domain helpers through credential samples stored in a

per-run vault and published through an authorization facet. Each listening

endpoint rematerialization yields a bind cookie. Sample fields include `uid`,

`supp_mask`, `bind_cookie`, `lane_key`, `mark`, and `seal_hex`.



## Rematerialization witness



Each shift cycle opens a rematerialization window. The catalog increments inode

generation when a shift arms; listener materialization seals the generation that

cookie minting must observe; cycle release closes the window without rewinding

inode generation. Cookie minting, listener creation, and catalog counters must

converge on the same sealed generation for every rematerialization. Closing a

shift must not rewind `inode_gen`. During an open shift, rematerialization must

consume the post-shift generation counter without decrementing it.



`inode_gen` is initialized to `1` when the catalog loads. Each rematerialization

increments `inode_gen` by exactly `1` before the listener seals that cycle's

generation. The first rematerialization therefore seals generation `1`, the

second seals `2`, and so on. `inode_gen` never rewinds and never skips a step.



Listener materialization must seal a generation before journal `rebind` rows may

be emitted. The witness records the sealed generation and the attach

`policy_epoch` observed at seal time.



## Digests



`bind_cookie` is the first 16 hex characters of SHA-256 over:



```

{path}|{inode_gen}|{attach_policy_epoch}

```



`inode_gen` is the sealed listener generation for the rematerialization that

minted the cookie. `attach_policy_epoch` is the `policy_epoch` stamped on the

attach binding row in the same export cycle.



Vault lookup keys for attach refs are the first 16 hex characters of SHA-256 over:



```

{slot_ref}|{bind_cookie}

```



Vault lookup keys for child refs that share a path with an attach ref are the

first 16 hex characters of SHA-256 over:



```

{slot_ref}|{bind_cookie}|{attach_policy_epoch}

```



`seal_hex` is the first 16 hex characters of SHA-256 over:



```

{slot_ref}|{path}|{bind_cookie}|{uid}|{supp_mask}|{mark}

```



Lane fingerprints must be derived from supplemental masks **after** drop-bit

clearing when the active mark advances.



`mark_digest_hex` is the first 16 hex characters of SHA-256 over `tag:uid`.

`path_digest_hex` is the first 32 hex characters of SHA-256 over path bytes.



## Authorization views



The vault holds the pin-eligible sample for a `(slot_ref, bind_cookie)` pair on

attach refs and for `(slot_ref, bind_cookie, attach_policy_epoch)` on child refs.

The authorization facet is the published view used by dual-view probes. After

any sample stamp or principal advance, the facet must reflect that live sample

(uid, supplemental mask, cookie, and seal). Republishing must occur whenever

`supp_mask` or `seal_hex` changes under the same bind cookie and uid, not only

when uid or cookie changes. The facet must retain the attach `slot_ref` through

mark advance so alpha attach probes can reach `seal_match` 1.



When the active mark advances, live samples must clear every bit set in

`drop_mask` from `supp_mask` before adopting the next mark uid, then recompute

`seal_hex` under the live bind cookie and slot using the cleared mask.



A helper ref that shares a filesystem path with its parent must still receive a

distinct vault key and a distinct `seal_hex` because `slot_ref` participates in

lane fingerprints and child vault keys bind the attach `policy_epoch`. Vault key

composition must use the helper ref's own `slot_ref` token, not an alias of the

attach ref.



Within each export cycle, attach ref binding rows stamp `policy_epoch` at the

attach bind instant. Child ref rows in that same cycle must carry a

`policy_epoch` exactly one greater than the attach row stamped in that cycle,

using the attach bind snapshot rather than any later counter movement in the

cycle.



Samples stamped under a prior bind cookie must not pin identity after the

listener cookie advances.



## Journal and resume



Across a multi-cycle export the journal keeps exactly one `intake` row for the

steady attach and exactly one `rebind` row when the active mark advances. The

`rebind` row may be recorded only after listener materialization has sealed a

generation for that cycle. Each journal row carries `op`, `slot_ref`, `mark`,

`seal_hex`, `supp_mask`, `policy_epoch`, and `bind_cookie`.



When `/app/output/binding_transcript.json` already contains rows, re-invoking

`gated` must leave binding_transcript, auth_trace, probe_report, auth_journal,

and converge_report unchanged — zero net row additions and identical per-slot

`policy_epoch` sequences.



## Cross-view agreement



`auth_trace.json` principal rows, `probe_report.jsonl` dual-view lines, and

`auth_journal.jsonl` must agree on the post-transition uid, mark, supplemental

mask, bind cookie, and lane fingerprint after a converged replay. Probe

`seal_match` is 1 only when the vault sample for the live cookie aligns with the

published facet on uid, supplemental mask, cookie, and seal. A sibling

`slot_ref` line pins that ref's vault sample against the active authorization

facet on the attach ref, so matching uids with distinct lane fingerprints keep

`seal_match` at 0 even when uids agree. `cred_gap` is

`current_uid - pinned_uid`. `converge_report.json` tallies scope agreement across

cookie alignment, sibling isolation, journal once-semantics, facet alignment,

and cleared drop bits.


