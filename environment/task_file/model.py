from __future__ import annotations

from pathlib import Path


def read_case(path: str | Path) -> dict[str, object]:
    params: dict[str, int] = {}
    rows: dict[str, list[list[str]]] = {
        "WAVE": [],
        "PACKAGE": [],
        "DEP": [],
        "BRIDGE": [],
    }
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "PARAM":
            params[parts[1]] = int(parts[2])
        else:
            rows[parts[0]].append(parts[1:])
    return {"params": params, **rows}


if __name__ == "__main__":
    case = read_case("/app/task_file/scan_input/abi_case.txt")
    print({key: len(value) if isinstance(value, list) else value for key, value in case.items()})
