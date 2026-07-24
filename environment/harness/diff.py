import glob
import subprocess
import sys

REFERENCE = "/app/bin/timers"
CANDIDATE = "/app/build/recovered"


def run(binary, data):
    done = subprocess.run([binary], input=data, capture_output=True, check=False)
    return done.returncode, done.stdout


def main():
    paths = sys.argv[1:] or sorted(glob.glob("/app/inputs/*.bin"))
    for path in paths:
        with open(path, "rb") as handle:
            data = handle.read()
        want_code, want = run(REFERENCE, data)
        got_code, got = run(CANDIDATE, data)
        if (want_code, want) == (got_code, got):
            continue
        print(f"differ: {path}")
        print(f"exit reference={want_code} candidate={got_code}")
        want_lines = want.decode("ascii", "replace").splitlines()
        got_lines = got.decode("ascii", "replace").splitlines()
        for i in range(max(len(want_lines), len(got_lines))):
            a = want_lines[i] if i < len(want_lines) else "<missing>"
            b = got_lines[i] if i < len(got_lines) else "<missing>"
            if a != b:
                print(f"line {i + 1} reference: {a}")
                print(f"line {i + 1} candidate: {b}")
                break
        return 1
    print(f"match on {len(paths)} traces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
