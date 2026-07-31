#!/bin/bash
set -euo pipefail

# Install the reconciler the fleet will ship, then close out this box with it.

install -d -m 0755 /usr/local/sbin

cat > /usr/local/sbin/dpx-reconcile <<'RECONCILE'
#!/usr/bin/env python3
"""dpx-reconcile -- close out an interrupted DPX/1 transaction on a root.

Usage: dpx-reconcile <root>

Exits 0 when the root is left consistent, 1 otherwise.
"""

import hashlib
import json
import os
import sys

DB_DIR = "var/lib/dpx/db"
JOURNAL_DIR = "var/lib/dpx/journal"
PART = ".dpx-part"
NEW = ".dpxnew"

RESERVED = {
    "/", "/bin", "/sbin", "/lib", "/etc", "/opt", "/srv",
    "/usr", "/usr/bin", "/usr/sbin", "/usr/lib", "/usr/libexec", "/usr/share",
    "/usr/local", "/usr/local/bin", "/usr/local/sbin", "/usr/local/lib",
    "/usr/local/share",
    "/var", "/var/lib", "/var/cache", "/var/log", "/var/lib/dpx", "/var/cache/dpx",
}


def real(root, path):
    return os.path.join(root, path.lstrip("/"))


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --- database -------------------------------------------------------------


def packages(root):
    base = real(root, "/" + DB_DIR)
    if not os.path.isdir(base):
        return []
    return sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)))


def read_meta(root, pkg):
    out = {}
    with open(real(root, f"/{DB_DIR}/{pkg}/meta")) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line:
                key, _, value = line.partition(": ")
                out[key] = value
    return out


def read_manifest(root, pkg):
    entries = []
    with open(real(root, f"/{DB_DIR}/{pkg}/manifest")) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            kind, mode, ref, flags, path = line.split(" ", 4)
            entries.append(
                {"kind": kind, "mode": mode, "ref": ref, "config": flags == "c", "path": path}
            )
    return entries


def write_meta(root, pkg, version, txid):
    path = real(root, f"/{DB_DIR}/{pkg}/meta")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(f"name: {pkg}\nversion: {version}\ninstalled-txid: {txid}\n")
    os.chmod(path, 0o644)


def write_manifest(root, pkg, entries):
    path = real(root, f"/{DB_DIR}/{pkg}/manifest")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for e in sorted(entries, key=lambda x: x["path"]):
            flags = "c" if e["config"] else "-"
            fh.write(f"{e['kind']} {e['mode']} {e['ref']} {flags} {e['path']}\n")
    os.chmod(path, 0o644)


def write_index(root):
    lines = []
    for pkg in packages(root):
        for e in read_manifest(root, pkg):
            lines.append(f"{e['path']} {pkg}\n")
    path = real(root, f"/{DB_DIR}/index")
    with open(path, "w") as fh:
        fh.writelines(sorted(lines))
    os.chmod(path, 0o644)


# --- journal --------------------------------------------------------------


def current_txid(root):
    path = real(root, f"/{JOURNAL_DIR}/current")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return fh.read().strip() or None


def journal_records(root, txid):
    out = []
    with open(real(root, f"/{JOURNAL_DIR}/{txid}.jrn")) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def all_journal_paths(root):
    base = real(root, "/" + JOURNAL_DIR)
    seen = set()
    if not os.path.isdir(base):
        return seen
    for name in sorted(os.listdir(base)):
        if name.endswith(".jrn"):
            for rec in journal_records(root, name[:-4]):
                if "path" in rec:
                    seen.add(rec["path"])
    return seen


# --- filesystem -----------------------------------------------------------


def prune(root, path):
    """Drop ancestor directories of path that are now empty."""
    d = os.path.dirname(path)
    while d and d not in RESERVED:
        target = real(root, d)
        if not os.path.isdir(target) or os.path.islink(target) or os.listdir(target):
            break
        os.rmdir(target)
        d = os.path.dirname(d)


def drop(root, path):
    target = real(root, path)
    if os.path.lexists(target):
        if os.path.isdir(target) and not os.path.islink(target):
            os.rmdir(target)
        else:
            os.remove(target)
    prune(root, path)


def scan_roots(root, known):
    tops = []
    for d in sorted({os.path.dirname(p) for p in known}):
        if any(d == t or d.startswith(t.rstrip("/") + "/") for t in tops):
            continue
        tops.append(d)
    return tops


def stray_parts(root):
    """Every .dpx-part still sitting under a directory DPX/1 keeps files in."""
    known = set(all_journal_paths(root))
    for pkg in packages(root):
        known.update(e["path"] for e in read_manifest(root, pkg))
    found = []
    for top in scan_roots(root, known):
        base = real(root, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            rel = "/" + os.path.relpath(dirpath, root).replace(os.sep, "/")
            rel = "/" if rel == "/." else rel
            for name in list(filenames) + list(dirnames):
                if name.endswith(PART):
                    found.append(os.path.join(rel, name))
    return sorted(found, key=len, reverse=True)


# --- closing a transaction ------------------------------------------------


def owned_elsewhere(root, pkg, path):
    for other in packages(root):
        if other == pkg:
            continue
        if any(e["path"] == path for e in read_manifest(root, other)):
            return True
    return False


def commit(root, entry, previous):
    """Move one staged file into place, honouring the config-file promise."""
    src = real(root, entry["path"] + PART)
    dst = real(root, entry["path"])
    prior = previous.get(entry["path"])
    if entry["config"] and prior is not None:
        if not os.path.lexists(dst):
            modified = False
        elif os.path.islink(dst) or not os.path.isfile(dst):
            modified = True
        else:
            modified = digest(dst) != prior["ref"]
        if modified:
            offer = real(root, entry["path"] + NEW)
            os.makedirs(os.path.dirname(offer), exist_ok=True)
            if os.path.lexists(offer):
                os.remove(offer)
            os.replace(src, offer)
            os.chmod(offer, int(entry["mode"], 8))
            return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.lexists(dst):
        os.remove(dst)
    os.replace(src, dst)
    if entry["kind"] != "l":
        os.chmod(dst, int(entry["mode"], 8))


def finish_package(root, txid, records, plan):
    pkg = plan["pkg"]
    staged = [r for r in records if r["op"] == "file-stage" and r["pkg"] == pkg]
    obsolete = [r["path"] for r in records if r["op"] == "file-obsolete" and r["pkg"] == pkg]
    stage_done = any(r["op"] == "stage-done" and r["pkg"] == pkg for r in records)
    swapped = any(r["op"] == "db-swap" and r["pkg"] == pkg for r in records)

    if not stage_done:
        # The new file set was never finished, so the installed version stands and the
        # half-written staging goes. Anything staged without a record for it is caught
        # by the sweep at the end.
        for rec in staged:
            drop(root, rec["path"] + PART)
        return

    entries = [
        {
            "kind": r["kind"],
            "mode": r["mode"],
            "ref": r["ref"],
            "config": bool(r["config"]),
            "path": r["path"],
        }
        for r in staged
    ]
    if swapped:
        # Everything up to and including the record swap happened; only the index is
        # behind, and that is rebuilt for the whole root at the end.
        return

    previous = {e["path"]: e for e in read_manifest(root, pkg)}
    for entry in entries:
        # A logged commit may or may not have been carried out. The sidecar decides.
        if os.path.lexists(real(root, entry["path"] + PART)):
            commit(root, entry, previous)
    for path in obsolete:
        if owned_elsewhere(root, pkg, path):
            continue
        drop(root, path)
    write_meta(root, pkg, plan["to"], txid)
    write_manifest(root, pkg, entries)


def close_transaction(root, txid):
    records = journal_records(root, txid)
    done = {r["pkg"] for r in records if r["op"] == "pkg-done"}
    for plan in [r for r in records if r["op"] == "pkg-plan"]:
        if plan["pkg"] not in done:
            finish_package(root, txid, records, plan)
    if not records or records[-1]["op"] != "txn-end":
        seq = records[-1]["seq"] + 1 if records else 1
        line = json.dumps({"seq": seq, "op": "txn-end", "txid": txid}, separators=(",", ":"))
        with open(real(root, f"/{JOURNAL_DIR}/{txid}.jrn"), "a") as fh:
            fh.write(line + "\n")
    marker = real(root, f"/{JOURNAL_DIR}/current")
    if os.path.exists(marker):
        os.remove(marker)


# --- self check -----------------------------------------------------------


def problems(root):
    out = []
    owners = {}
    for pkg in packages(root):
        for e in read_manifest(root, pkg):
            owners.setdefault(e["path"], []).append(pkg)
            target = real(root, e["path"])
            if not os.path.lexists(target):
                out.append(f"missing {e['path']}")
                continue
            if e["kind"] == "l":
                if not os.path.islink(target) or os.readlink(target) != e["ref"]:
                    out.append(f"bad link {e['path']}")
                continue
            if os.path.islink(target) or not os.path.isfile(target):
                out.append(f"not a regular file {e['path']}")
                continue
            if "%04o" % (os.lstat(target).st_mode & 0o7777) != e["mode"]:
                out.append(f"wrong mode {e['path']}")
            if not e["config"] and digest(target) != e["ref"]:
                out.append(f"content differs {e['path']}")
    for path, pkgs in owners.items():
        if len(pkgs) > 1:
            out.append(f"claimed twice {path}")
    want = sorted(f"{e['path']} {pkg}\n" for pkg in packages(root) for e in read_manifest(root, pkg))
    index = real(root, f"/{DB_DIR}/index")
    if not os.path.exists(index) or open(index).readlines() != want:
        out.append("index out of date")
    if stray_parts(root):
        out.append("staged files left behind")
    if current_txid(root):
        out.append("transaction still current")
    return out


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: dpx-reconcile <root>\n")
        return 2
    root = os.path.abspath(argv[1])
    if not os.path.isdir(real(root, "/" + DB_DIR)):
        sys.stderr.write(f"dpx-reconcile: {root} is not a DPX/1 root\n")
        return 2

    txid = current_txid(root)
    if txid:
        close_transaction(root, txid)
    for path in stray_parts(root):
        drop(root, path)
    write_index(root)

    found = problems(root)
    for line in found:
        sys.stderr.write(f"dpx-reconcile: {line}\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
RECONCILE

chmod 0755 /usr/local/sbin/dpx-reconcile

/usr/local/sbin/dpx-reconcile /
