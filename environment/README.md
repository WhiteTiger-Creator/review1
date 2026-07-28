# Environment notes

The final stage uses the exact canonical Terminal-Bench Go image published in Dockerfile & Image Best Practices §2:

`public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac`

The Go toolchain remains in the final stage because both agents and the verifier rebuild the mixed Go/C project. The build verifies `/usr/local/go/bin/go` and exposes it through `/usr/bin/go`, so execution does not depend on an ambiguous shell path.

Pytest and NumPy are installed from Debian Bookworm with explicit package versions (`python3-pytest=7.2.1-2` and `python3-numpy=1:1.24.2-1+deb12u1`) and their imported versions are checked during the image build. SQLite comes from Python's standard library. FFTW, Python, tmux, asciinema, and the remaining verifier tools are installed in one bounded apt transaction. There are no pip, Go-module, or verifier-plugin downloads, and runtime network access is disabled.
