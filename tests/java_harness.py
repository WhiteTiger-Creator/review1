"""Compile and run Java verifier probes against /app/lib/glideclash.jar."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

JAR = Path("/app/lib/glideclash.jar")
PROBE_DIR = Path(__file__).resolve().parent / "java"


def run_probe(main_class: str, scenario: str, *extra: str) -> str:
    if not JAR.is_file():
        raise FileNotFoundError(f"missing jar: {JAR}")
    sources = sorted(PROBE_DIR.glob("*.java"))
    if not sources:
        raise FileNotFoundError(f"no probes in {PROBE_DIR}")
    tmp = Path(tempfile.mkdtemp(prefix="glideprobe_"))
    try:
        cmd_compile = [
            "javac",
            "--release",
            "17",
            "-cp",
            str(JAR),
            "-d",
            str(tmp),
            *[str(s) for s in sources],
        ]
        subprocess.run(cmd_compile, check=True, capture_output=True, text=True)
        cmd_run = [
            "java",
            "-cp",
            f"{tmp}{os.pathsep}{JAR}",
            main_class,
            scenario,
            *extra,
        ]
        proc = subprocess.run(cmd_run, check=True, capture_output=True, text=True)
        return proc.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
