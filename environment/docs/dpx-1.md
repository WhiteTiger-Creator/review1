# DPX/1 on-disk contract

Revision 11. Owner: platform/packaging. This describes the formats and the guarantees.
It is not a manual for the `dpx` binary — run `dpx --help` for that.

Everything below is written as an absolute path inside a **root**. On a normal machine
the root is `/`; test and staging roots are ordinary directories with the same layout
underneath them.

## 1. Layout

| path | what |
|---|---|
| `/var/lib/dpx/db/<pkg>/meta` | package record |
| `/var/lib/dpx/db/<pkg>/manifest` | the files the package owns |
| `/var/lib/dpx/db/index` | path-to-package index across all installed packages |
| `/var/lib/dpx/journal/<txid>.jrn` | one journal per transaction |
| `/var/lib/dpx/journal/current` | names the transaction in flight, absent when none is |
| `/var/cache/dpx/pkgs/<pkg>-<ver>.dpk` | package archives |

## 2. Record formats

`meta` is three lines, in this order:

```
name: netcfg
version: 1.4.2
installed-txid: T-2390
```

`manifest` is one line per owned path, `<kind> <mode> <ref> <flags> <path>`, sorted by
path, newline-terminated. `kind` is `f` for a regular file or `l` for a symlink. `mode`
is four octal digits, and is `0777` for a symlink. `ref` is the sha256 of the content for
`f` and the link target for `l`. `flags` is `c` for a config file and `-` otherwise. DPX/1
paths and link targets never contain whitespace.

`index` is one line per owned path, `<path> <pkg>`, sorted, covering every installed
package. It is derived state: it must agree with the manifests at all times.

A `.dpk` archive is a tar holding `PKGINFO`, `MANIFEST` in the format above, and the
package's files under `data/`.

## 3. Ownership

A path is owned by exactly one installed package — the one whose manifest names it. DPX/1
never removes a path that an installed package owns, and never leaves two packages
claiming the same path once a transaction has finished.

Ownership can move between packages: a file dropped by one package's new version and
picked up by another's is normal, and during the transaction that moves it both records
briefly name it.

## 4. Config files

A manifest entry flagged `c` is a config file. The operator is allowed to edit it, so its
content is permitted to drift from the `ref` its manifest records; that is a locally
modified config, not damage.

DPX/1's promise on upgrade is that an operator's edits are never overwritten. When a
config file is replaced by a newer version:

- if the file on disk still matches the `ref` recorded by the **version being replaced**,
  the new content is installed over it;
- otherwise the file on disk is left exactly as it is and the new content is installed
  beside it as `<path>.dpxnew`, at the mode the new manifest gives. Any `.dpxnew` already
  sitting there from an earlier upgrade is replaced.

A path that is missing, or that is not a regular file, counts as not matching. A config
file the version being replaced did not own is installed directly.

## 5. Directories

DPX/1 creates the directories it needs, mode 0755, and removes a directory once it is
empty. It never removes any of:

```
/  /bin  /sbin  /lib  /etc  /opt  /srv
/usr  /usr/bin  /usr/sbin  /usr/lib  /usr/libexec  /usr/share
/usr/local  /usr/local/bin  /usr/local/sbin  /usr/local/lib  /usr/local/share
/var  /var/lib  /var/cache  /var/log  /var/lib/dpx  /var/cache/dpx
```

## 6. Transactions

A transaction upgrades a list of packages, one package at a time, in the order the
`txn-begin` record lists. A package is taken through five stages:

**Stage.** Each file of the new version is written next to where it will live, under the
name `<path>.dpx-part`, mode 0600 whatever the manifest says. Symlinks are staged as
symlinks. Then the paths the version being replaced owns and the new version does not are
noted as obsolete. Staging touches nothing that is already installed.

**Commit.** Every staged file is moved into place, in the order it was staged, taking the
kind and mode its manifest entry gives, and config files are handled as in section 4.

**Sweep.** The obsolete paths are removed, subject to section 3, and section 5 applies to
the directories that empties.

**Swap.** The package's `meta` and `manifest` are replaced by those of the new version,
with `installed-txid` set to the transaction. This is atomic.

**Index.** `/var/lib/dpx/db/index` is rebuilt from the installed packages.

## 7. Journal

The journal is append-only JSON, one record per line, `seq` counting from 1. A record is
never rewritten or removed once written.

| op | fields | meaning |
|---|---|---|
| `txn-begin` | `txid` `kind` `packages` | the transaction and everything it intends to touch |
| `pkg-plan` | `pkg` `from` `to` | this package is being taken from one version to another |
| `file-stage` | `pkg` `path` `kind` `mode` `ref` `config` | a file of the new version, as its manifest entry |
| `file-obsolete` | `pkg` `path` | a path the new version does not own |
| `stage-done` | `pkg` | staging finished |
| `commit-begin` | `pkg` | the commit is starting |
| `file-commit` | `pkg` `path` | this file is being moved into place |
| `file-remove` | `pkg` `path` | this obsolete path is being swept |
| `commit-done` | `pkg` | commit and sweep finished |
| `db-swap` | `pkg` | the record and manifest are the new version's |
| `pkg-done` | `pkg` | the index has been rebuilt and the package is finished |
| `txn-end` | `txid` | the transaction is closed |

Ordering matters and is not uniform. `file-commit` and `file-remove` are written **before**
the change they describe, so the last one in a journal may or may not have been carried
out. Every other record is written **after** what it describes, so its presence means the
thing happened.

## 8. Interrupted transactions

A machine that loses power mid-transaction comes up with `current` still naming the
transaction and its journal ending wherever the machine stopped.

Such a transaction is **closed, not resumed**. Closing it means:

- the package that was in flight ends up wholly at one of its two versions, with the
  record, the manifest, the index, the installed files and the guarantees of sections 3, 4
  and 5 all agreeing on which;
- which of the two is decided by staging. Once `stage-done` is on record every file of the
  new version exists on disk, so the new version is what the transaction is committed to.
  Before that record the new content is incomplete, so the version already installed
  stands and the half-written staging is discarded;
- packages the transaction named but had not begun are not begun now. A transaction is
  never picked up again after it is closed;
- `current` is removed and a `txn-end` record is appended to the journal.

Journals of transactions that already carry `txn-end` describe finished work and are
history.

## 9. Consistency

A root is consistent when every installed package's manifest agrees with what is on disk —
each path present, of the recorded kind and mode, and for anything but a config file of
the recorded content — the index agrees with the manifests, no path is claimed twice, no
`.dpx-part` is left anywhere, every `.dpxnew` sits beside a config entry, and no
transaction is marked current. `dpx verify` reports on exactly that; a locally modified
config is reported `M` and is not an inconsistency.

## 10. `dpx install --force`

`--force` writes every file an archive carries and takes over the package record. It is a
repair hatch for a machine that has lost its files. It does not read the installed
manifest, it does not apply section 4, and it does not sweep. Nothing else in this
document describes it.
