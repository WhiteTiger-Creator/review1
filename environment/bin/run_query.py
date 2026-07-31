import os
import signal
import sys

import kuzu

DEFAULT_GRAPH_PATH = "/app/graph/argumentation.kuzu"
BUFFER_POOL_BYTES = 512 * 1024 * 1024
QUERY_TIMEOUT_SEC = 300


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
        sys.stderr.write("usage: run_query.py '<cypher query text>'\n")
        return 2

    query_text = sys.argv[1]
    graph_path = os.environ.get("GRAPH_DB_PATH", DEFAULT_GRAPH_PATH)

    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(QUERY_TIMEOUT_SEC)

    try:
        columns, rows = run(query_text, graph_path)
    except QueryTimeout as exc:
        sys.stderr.write(str(exc) + "\n")
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
