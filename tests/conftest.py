import os
import shutil

import pytest

DB_PATH = "/app/wb.db"
OUTPUT_DIR = "/app/output"


def _wipe_state():
    # Remove the sqlite db and any journal/WAL/shm siblings it may have left
    # behind from an abrupt prior shutdown.
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)
    if os.path.isdir(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)


@pytest.fixture(scope="session", autouse=True)
def _reset_state_before_session():
    """
    Unconditionally wipe any pre-existing /app/wb.db (plus -journal/-wal/-shm
    siblings) and /app/output/ before the test session starts.

    This guards against leftover on-disk state surviving into this test
    run -- e.g. if the evaluation harness reuses a container/filesystem
    across sequential trials, a stale wb.db created under an older schema
    would make `CREATE TABLE IF NOT EXISTS` a no-op (leaving old columns
    missing), and a stale pipeline_report.json could linger from a
    previous run. Wiping unconditionally at session start ensures every
    run starts from a clean, freshly-initialized filesystem regardless of
    what a prior run left behind.
    """
    _wipe_state()
    yield
