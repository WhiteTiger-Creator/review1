"""Verifier-owned Cypher runner.

The agent-facing runner under /app/bin is writable by the agent, so the
verifier must never execute it: replacing it with something that prints the
expected rows would pass the whole suite without answering the question. This
copy lives in the read-only test directory and is the only runner the verifier
invokes.

Usage: verifier_runner.py '<cypher query text>'
Reads the database path from GRAPH_DB_PATH.
"""

import os
import signal
import sys

import kuzu

QUERY_TIMEOUT_SEC = 300
BUFFER_POOL_BYTES = 512 * 1024 * 1024


class QueryTimeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise QueryTimeout(f"query exceeded the {QUERY_TIMEOUT_SEC}s runner timeout")


def run(query_text, graph_path):
    db = kuzu.Database(graph_path, read_only=True, buffer_pool_size=BUFFER_POOL_BYTES)
    conn = kuzu.Connection(db)
    result = conn.execute(query_text)
    columns = result.get_column_names()
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    return columns, rows


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: verifier_runner.py '<cypher query text>'\n")
        return 2

    query_text = sys.argv[1]
    graph_path = os.environ.get("GRAPH_DB_PATH")
    if not graph_path:
        sys.stderr.write("GRAPH_DB_PATH is not set\n")
        return 2

    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(QUERY_TIMEOUT_SEC)

    try:
        columns, rows = run(query_text, graph_path)
    except QueryTimeout as exc:
        sys.stderr.write(f"{exc}\n")
        return 3
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"query failed: {exc}\n")
        return 1
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)

    print("\t".join(columns))
    for row in rows:
        print("\t".join("" if value is None else str(value) for value in row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
