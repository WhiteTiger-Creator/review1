"""Verifier for the DPX/1 reconcile task.

The file is in two halves.

The first half is preservation: what was on this box before anyone touched it and has to
survive whatever the recovery does. Those checks pass on an untouched box and have to keep
passing, so they never invoke the reconciler.

The second half is reconciliation: the state of this box's root after recovery, and the
state of four held-out roots the verifier materialises itself and runs the delivered
/usr/local/sbin/dpx-reconcile against. Nothing here trusts the on-box dpx binary; the
consistency rules are re-implemented below.
"""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

RECONCILE = "/usr/local/sbin/dpx-reconcile"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
WORK = Path("/tmp/dpx-verifier")

# A reconciler answers any of these roots in well under a second. The cap is only here so
# that a submission which loops forever fails its tests instead of eating the budget.
RUN_TIMEOUT = 120

LIVE = json.loads((FIXTURES / "live_expect.json").read_text())
HOLDOUTS = ["a", "b", "c", "d"]

DB = "var/lib/dpx/db"
JOURNAL = "var/lib/dpx/journal"


# ---------------------------------------------------------------------------
# reading trees
# ---------------------------------------------------------------------------


def content(entry):
    """The bytes a fixture entry stands for. Text stays readable, archives are hex."""
    if "text" in entry:
        return entry["text"].encode()
    return bytes.fromhex(entry["hex"])


def node_of(root, rel):
    """Describe one path the same way the fixtures do."""
    target = root / rel.lstrip("/")
    if target.is_symlink():
        return {"path": rel, "kind": "l", "target": os.readlink(target)}
    st = target.lstat()
    entry = {"path": rel, "kind": "f", "mode": "%04o" % (st.st_mode & 0o7777)}
    body = target.read_bytes()
    try:
        text = body.decode()
        if "\x00" in text:
            raise ValueError
        entry["text"] = text
    except (UnicodeDecodeError, ValueError):
        entry["hex"] = body.hex()
    return entry


def snapshot(root, prefixes=None):
    """Read a real tree into the fixture shape, over the whole root or given subtrees."""
    dirs = set()
    entries = []

    def walk(rel):
        dirs.add(rel)
        base = root / rel.lstrip("/")
        for name in sorted(os.listdir(base)):
            child = (rel.rstrip("/") or "") + "/" + name
            path = root / child.lstrip("/")
            if path.is_symlink() or not path.is_dir():
                entries.append(node_of(root, child))
            else:
                walk(child)

    for rel in ["/"] if prefixes is None else prefixes:
        path = root / rel.lstrip("/")
        if not path.is_symlink() and not path.exists():
            continue
        if path.is_symlink() or not path.is_dir():
            entries.append(node_of(root, rel))
        else:
            walk(rel)
    return {"dirs": sorted(dirs), "entries": sorted(entries, key=lambda e: e["path"])}


def without_dpx_state(snap):
    """Drop the database, journal and package cache; each is compared on its own terms."""

    def hidden(path):
        return any(
            path == base or path.startswith(base + "/")
            for base in ("/var/lib/dpx", "/var/cache/dpx")
        )

    return {
        "dirs": [d for d in snap["dirs"] if not hidden(d)],
        "entries": [e for e in snap["entries"] if not hidden(e["path"])],
    }


def brief(entry):
    if entry["kind"] == "l":
        return "symlink -> " + entry["target"]
    body = content(entry)
    return f"mode {entry['mode']}, {len(body)} bytes {body[:48]!r}"


def differences(actual, expected):
    """A readable account of how two trees disagree."""
    got = {e["path"]: e for e in actual["entries"]}
    want = {e["path"]: e for e in expected["entries"]}
    out = []
    for path in sorted(set(want) - set(got)):
        out.append(f"missing {path} ({brief(want[path])})")
    for path in sorted(set(got) - set(want)):
        out.append(f"unexpected {path} ({brief(got[path])})")
    for path in sorted(set(got) & set(want)):
        if got[path] != want[path]:
            out.append(f"wrong {path}: got {brief(got[path])}, wanted {brief(want[path])}")
    for d in sorted(set(expected["dirs"]) - set(actual["dirs"])):
        out.append(f"missing directory {d}")
    for d in sorted(set(actual["dirs"]) - set(expected["dirs"])):
        out.append(f"unexpected directory {d}")
    return out


# ---------------------------------------------------------------------------
# reading the database
# ---------------------------------------------------------------------------


def by_path(entries):
    """Manifest entries in a fixed order, so two manifests can be compared directly."""
    return sorted(entries, key=lambda entry: entry["path"])


def parse_manifest(text):
    entries = []
    for line in text.splitlines():
        if not line:
            continue
        kind, mode, ref, flags, path = line.split(" ", 4)
        entries.append(
            {"kind": kind, "mode": mode, "ref": ref, "config": flags == "c", "path": path}
        )
    return entries


def read_db(root):
    base = root / DB
    out = {}
    for name in sorted(os.listdir(base)):
        pkg_dir = base / name
        if not pkg_dir.is_dir():
            continue
        meta = {}
        for line in (pkg_dir / "meta").read_text().splitlines():
            if line:
                key, _, value = line.partition(": ")
                meta[key] = value
        body = (pkg_dir / "manifest").read_text()
        out[name] = {
            "version": meta.get("version"),
            "txid": meta.get("installed-txid"),
            "manifest": parse_manifest(body),
            "raw": body,
        }
    return out


def compare_db(root, expected):
    """Check the package records against what the transaction should have left."""
    actual = read_db(root)
    assert sorted(actual) == sorted(expected), (
        f"installed packages {sorted(actual)} != expected {sorted(expected)}"
    )
    for name, want in sorted(expected.items()):
        got = actual[name]
        assert got["version"] == want["version"], (
            f"{name} is at version {got['version']}, expected {want['version']}"
        )
        assert got["txid"] == want["txid"], (
            f"{name} records transaction {got['txid']}, expected {want['txid']}"
        )
        assert by_path(got["manifest"]) == by_path(want["manifest"]), (
            f"{name} manifest does not describe the installed version"
        )
        paths = [e["path"] for e in got["manifest"]]
        assert paths == sorted(paths), f"{name} manifest is not sorted by path"
        assert got["raw"].endswith("\n"), f"{name} manifest is not newline terminated"

    want_index = sorted(
        f"{e['path']} {name}\n" for name, rec in actual.items() for e in rec["manifest"]
    )
    index = root / DB / "index"
    assert index.exists(), "the database index is missing"
    assert index.read_text().splitlines(keepends=True) == want_index, (
        "the database index does not match the installed manifests"
    )


# ---------------------------------------------------------------------------
# running the delivered reconciler
# ---------------------------------------------------------------------------


def run_reconcile(root):
    assert Path(RECONCILE).is_file(), f"{RECONCILE} was not delivered"
    assert os.access(RECONCILE, os.X_OK), f"{RECONCILE} is not executable"
    try:
        return subprocess.run(
            [RECONCILE, str(root)],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=RUN_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError(f"{RECONCILE} did not finish within {RUN_TIMEOUT}s on {root}") from None


def materialise(tree, dest, cache=None):
    """Write a fixture's broken root out as a real directory."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if cache is not None:
        pkgs = dest / "var/cache/dpx/pkgs"
        pkgs.mkdir(parents=True)
        for archive in sorted(cache.iterdir()):
            shutil.copy2(archive, pkgs / archive.name)
    for rel in tree["dirs"]:
        (dest / rel.lstrip("/")).mkdir(parents=True, exist_ok=True)
    for entry in tree["entries"]:
        path = dest / entry["path"].lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        if entry["kind"] == "l":
            if path.is_symlink() or path.exists():
                path.unlink()
            os.symlink(entry["target"], path)
        else:
            path.write_bytes(content(entry))
            os.chmod(path, int(entry["mode"], 8))


_runs = {}


def holdout(name, passes=1):
    """Materialise a held-out root, reconcile it, and cache the outcome."""
    key = (name, passes)
    if key not in _runs:
        data = json.loads((FIXTURES / f"holdout_{name}.json").read_text())
        root = WORK / f"{name}-{passes}"
        materialise(data["root"], root, cache=FIXTURES / "cache" / name)
        results = [run_reconcile(root) for _ in range(passes)]
        _runs[key] = (data, root, results)
    return _runs[key]


def live_text(path):
    """The content the expected live tree gives for a path."""
    for entry in LIVE["tree"]["entries"]:
        if entry["path"] == path:
            return content(entry)
    raise KeyError(path)


# ===========================================================================
# preservation -- true of the box before recovery, and still true after
# ===========================================================================


def test_local_edit_to_the_netcfg_config_survives():
    """The hand-edited /etc/netcfg/netcfg.conf keeps its operator content, byte for byte."""
    path = Path("/etc/netcfg/netcfg.conf")
    assert path.is_file(), "/etc/netcfg/netcfg.conf is gone"
    assert path.read_bytes() == live_text("/etc/netcfg/netcfg.conf"), (
        "the local edits to /etc/netcfg/netcfg.conf were overwritten"
    )


def test_local_edit_to_the_hostkit_config_survives():
    """The hand-edited /etc/hostkit/hostkit.conf keeps its operator content."""
    path = Path("/etc/hostkit/hostkit.conf")
    assert path.is_file(), "/etc/hostkit/hostkit.conf is gone"
    assert path.read_bytes() == live_text("/etc/hostkit/hostkit.conf"), (
        "the local edits to /etc/hostkit/hostkit.conf were overwritten"
    )


def test_offer_left_by_the_finished_package_survives():
    """The .dpxnew the completed leg of the run already produced is still there, unchanged."""
    path = Path("/etc/hostkit/hostkit.conf.dpxnew")
    assert path.is_file(), "/etc/hostkit/hostkit.conf.dpxnew was destroyed"
    assert path.read_bytes() == live_text("/etc/hostkit/hostkit.conf.dpxnew")
    assert "%04o" % (path.lstat().st_mode & 0o7777) == "0644"


@pytest.mark.parametrize("pkg", ["crumb", "sift"])
def test_packages_outside_the_run_are_untouched(pkg):
    """Packages the interrupted run never named keep their record and their files."""
    root = Path("/")
    got = read_db(root)[pkg]
    want = LIVE["db"][pkg]
    assert got["version"] == want["version"]
    assert got["txid"] == want["txid"]
    for entry in want["manifest"]:
        path = root / entry["path"].lstrip("/")
        assert path.exists(), f"{pkg} lost {entry['path']}"
        assert "%04o" % (path.lstat().st_mode & 0o7777) == entry["mode"]


@pytest.mark.parametrize("pkg", ["zoneprep", "plait"])
def test_packages_the_run_never_began_stay_where_they_were(pkg):
    """A package the run listed but never started is left at its installed version."""
    got = read_db(Path("/"))[pkg]
    want = LIVE["db"][pkg]
    assert got["version"] == want["version"], (
        f"{pkg} was moved to {got['version']}; the run never began it"
    )
    assert got["txid"] == want["txid"]


def test_cached_archives_are_untouched():
    """Nothing in the package cache is added, removed or rewritten."""
    cache = Path("/var/cache/dpx/pkgs")
    assert sorted(p.name for p in cache.iterdir()) == sorted(LIVE["cache"])
    for name, want in sorted(LIVE["cache"].items()):
        got = hashlib.sha256((cache / name).read_bytes()).hexdigest()
        assert got == want, f"{name} was rewritten"


@pytest.mark.parametrize("name", ["T-2390.jrn", "T-2417.jrn"])
def test_journal_history_is_not_rewritten(name):
    """Journals are append-only: the records already on disk stay exactly as they were."""
    body = (Path("/var/lib/dpx/journal") / name).read_text()
    original = LIVE["journals"][name]
    assert body.startswith(original), (
        f"{name} no longer begins with the records it had; journal history was edited"
    )


def test_completed_journal_is_not_reopened():
    """The transaction that already carried txn-end is not made current again."""
    body = (Path("/var/lib/dpx/journal/T-2390.jrn")).read_text()
    records = [json.loads(line) for line in body.splitlines() if line.strip()]
    assert records[-1]["op"] == "txn-end", "T-2390 no longer ends closed"
    assert [r["seq"] for r in records] == list(range(1, len(records) + 1))


# ===========================================================================
# reconciliation -- true only once the box has been put right
# ===========================================================================


def test_reconciler_is_delivered_and_runnable():
    """The fix ships as an executable at the path the rollout will call."""
    assert Path(RECONCILE).is_file(), f"{RECONCILE} was not delivered"
    assert os.access(RECONCILE, os.X_OK), f"{RECONCILE} is not executable"


def test_no_transaction_is_left_in_flight():
    """The interrupted run is closed: the marker is gone and its journal ends closed."""
    assert not Path("/var/lib/dpx/journal/current").exists(), (
        "a transaction is still marked current"
    )
    body = Path("/var/lib/dpx/journal/T-2417.jrn").read_text()
    records = [json.loads(line) for line in body.splitlines() if line.strip()]
    assert records[-1]["op"] == "txn-end", "T-2417 was never closed off"
    assert records[-1].get("txid") == "T-2417"
    seqs = [r["seq"] for r in records]
    assert seqs == sorted(set(seqs)), "journal sequence numbers do not keep increasing"


def test_no_staged_leftovers_remain_on_the_box():
    """Nothing staged by the interrupted run is still sitting next to its target."""
    strays = []
    for base in ["/etc", "/usr/bin", "/usr/lib", "/usr/share", "/var/lib/dpx", "/var/cache/dpx"]:
        for dirpath, dirnames, filenames in os.walk(base):
            for name in list(filenames) + list(dirnames):
                if name.endswith(".dpx-part"):
                    strays.append(os.path.join(dirpath, name))
    assert not strays, f"staged leftovers remain: {sorted(strays)}"


def test_live_tree_matches_the_completed_transaction():
    """Every file DPX/1 owns on this box is what the run would have left had it finished."""
    actual = without_dpx_state(snapshot(Path("/"), LIVE["prefixes"]))
    expected = without_dpx_state(LIVE["tree"])
    problems = differences(actual, expected)
    assert not problems, "the recovered tree is wrong:\n  " + "\n  ".join(problems)


def test_live_database_matches_the_completed_transaction():
    """Records, manifests and the index describe the versions actually installed."""
    compare_db(Path("/"), LIVE["db"])


def test_updated_config_is_offered_rather_than_forced():
    """The newer netcfg config lands beside the edited one instead of replacing it."""
    offer = Path("/etc/netcfg/netcfg.conf.dpxnew")
    assert offer.is_file(), "the packaged netcfg config was never offered"
    assert offer.read_bytes() == live_text("/etc/netcfg/netcfg.conf.dpxnew")
    assert "%04o" % (offer.lstat().st_mode & 0o7777) == "0644", (
        "the offered config did not take the mode its manifest gives"
    )


def test_file_whose_move_was_recorded_but_not_made_is_in_place():
    """/usr/lib/netcfg/rules.tbl holds the new version's content at its manifest mode."""
    path = Path("/usr/lib/netcfg/rules.tbl")
    assert path.read_bytes() == live_text("/usr/lib/netcfg/rules.tbl")
    assert "%04o" % (path.lstat().st_mode & 0o7777) == "0644"


def test_new_files_take_the_mode_their_manifest_gives():
    """Files the run had not reached are installed at their packaged modes."""
    for rel, mode in [
        ("/usr/share/netcfg/regions/ap.map", "0644"),
        ("/usr/lib/netcfg/libnet.so.1.5", "0644"),
        ("/usr/bin/netcfg", "0755"),
    ]:
        path = Path(rel)
        assert path.is_file(), f"{rel} was never installed"
        assert "%04o" % (path.lstat().st_mode & 0o7777) == mode, f"{rel} has the wrong mode"


def test_entry_that_became_a_symlink_is_a_symlink():
    """/usr/lib/netcfg/libnet.so.1 is installed as the link the new version ships."""
    path = Path("/usr/lib/netcfg/libnet.so.1")
    assert path.is_symlink(), "libnet.so.1 was not installed as a symlink"
    assert os.readlink(path) == "libnet.so.1.5"


def test_dropped_path_another_package_owns_is_kept():
    """A path the new version drops but another installed package claims stays put."""
    path = Path("/usr/lib/netcfg/shared/geo.dat")
    assert path.is_file(), "geo.dat was removed even though hostkit owns it"
    assert path.read_bytes() == live_text("/usr/lib/netcfg/shared/geo.dat")


def test_dropped_path_no_installed_package_owns_is_removed():
    """A path the new version drops and nothing installed claims is swept away."""
    assert not Path("/usr/lib/netcfg/shared/zones.idx").exists(), (
        "zones.idx survived; no installed package owns it"
    )
    assert not Path("/usr/share/netcfg/legacy.tbl").exists(), "legacy.tbl was not swept"


def test_directories_the_sweep_empties_are_removed():
    """A directory left empty by the sweep goes; one that still holds a file stays."""
    assert not Path("/usr/share/netcfg/tables").exists(), (
        "/usr/share/netcfg/tables is empty and should have been removed"
    )
    assert Path("/usr/share/netcfg").is_dir(), "/usr/share/netcfg still holds files"
    assert Path("/usr/lib/netcfg/shared").is_dir(), "/usr/lib/netcfg/shared still holds geo.dat"


def test_running_the_reconciler_again_on_this_box_changes_nothing():
    """A second pass over an already consistent root is a no-op that still exits 0."""
    before = snapshot(Path("/"), LIVE["prefixes"] + ["/var/lib/dpx/db"])
    proc = run_reconcile("/")
    assert proc.returncode == 0, (
        f"a second pass exited {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    after = snapshot(Path("/"), LIVE["prefixes"] + ["/var/lib/dpx/db"])
    problems = differences(after, before)
    assert not problems, "the second pass changed the box:\n  " + "\n  ".join(problems)


# --- held-out roots --------------------------------------------------------


@pytest.mark.parametrize("name", HOLDOUTS)
def test_holdout_root_is_reconciled_successfully(name):
    """The delivered reconciler exits 0 on a root it has never seen."""
    _, _, results = holdout(name)
    proc = results[-1]
    assert proc.returncode == 0, (
        f"reconciling holdout {name} exited {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


@pytest.mark.parametrize("name", HOLDOUTS)
def test_holdout_tree_matches_the_completed_transaction(name):
    """A held-out root ends up with exactly the files its transaction should have left."""
    data, root, _ = holdout(name)
    actual = without_dpx_state(snapshot(root))
    expected = without_dpx_state(data["expect"]["tree"])
    problems = differences(actual, expected)
    assert not problems, f"holdout {name} tree is wrong:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("name", HOLDOUTS)
def test_holdout_database_matches_the_completed_transaction(name):
    """A held-out root's records, manifests and index describe what is installed."""
    data, root, _ = holdout(name)
    compare_db(root, data["expect"]["db"])


@pytest.mark.parametrize("name", HOLDOUTS)
def test_holdout_transaction_is_closed_without_editing_history(name):
    """Each held-out root is left with no transaction current and its journals intact."""
    data, root, _ = holdout(name)
    assert not (root / JOURNAL / "current").exists(), (
        f"holdout {name} still has a transaction marked current"
    )
    originals = {
        os.path.basename(e["path"]): e["text"]
        for e in data["root"]["entries"]
        if e["path"].startswith("/" + JOURNAL) and e["path"].endswith(".jrn")
    }
    for filename, original in sorted(originals.items()):
        body = (root / JOURNAL / filename).read_text()
        assert body.startswith(original), f"holdout {name}: {filename} was rewritten"
        records = [json.loads(line) for line in body.splitlines() if line.strip()]
        assert records[-1]["op"] == "txn-end", f"holdout {name}: {filename} was left open"
        seqs = [r["seq"] for r in records]
        assert seqs == sorted(set(seqs)), f"holdout {name}: {filename} sequence numbers repeat"


@pytest.mark.parametrize("name", HOLDOUTS)
def test_holdout_cached_archives_are_untouched(name):
    """Recovery reads the package cache at most; it never rewrites or prunes it."""
    data, root, _ = holdout(name)
    pkgs = root / "var/cache/dpx/pkgs"
    assert sorted(p.name for p in pkgs.iterdir()) == sorted(data["cache"]), (
        f"holdout {name}: the package cache gained or lost archives"
    )
    for archive, want in sorted(data["cache"].items()):
        got = hashlib.sha256((pkgs / archive).read_bytes()).hexdigest()
        assert got == want, f"holdout {name}: {archive} was rewritten"


@pytest.mark.parametrize("name", HOLDOUTS)
def test_holdout_reconcile_is_idempotent(name):
    """Running the reconciler twice over a held-out root gives the same result as once."""
    data, root, results = holdout(name, passes=2)
    assert results[-1].returncode == 0, (
        f"the second pass over holdout {name} exited {results[-1].returncode}\n"
        f"stderr: {results[-1].stderr}"
    )
    actual = without_dpx_state(snapshot(root))
    expected = without_dpx_state(data["expect"]["tree"])
    problems = differences(actual, expected)
    assert not problems, f"holdout {name} drifted on a second pass:\n  " + "\n  ".join(problems)
    compare_db(root, data["expect"]["db"])
