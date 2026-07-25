# Justification: this task builds a multi-library CMake C++ project (GCC 13 +
# CMake + make) and cannot run on the Python or Node runtime bases. This is the
# canonical Terminal-Bench C/C++ (GCC) base image, digest-pinned to the approved
# public.ecr.aws GCC 13 bookworm reference.
FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c

RUN apt-get update && apt-get install -y --no-install-recommends \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    cmake=3.25.1-1 \
    make=4.3-4.1 \
    python3=3.11.2-1+b1 \
    python3-pip=23.0.1+dfsg-1 \
    python3-venv=3.11.2-1+b1 \
    tmux=3.3a-3 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir \
       pytest==8.4.1 \
       pytest-json-ctrf==0.3.5
RUN ln -sf /opt/verifier/bin/pytest /usr/local/bin/pytest

ENV PATH="/opt/verifier/bin:${PATH}"

COPY . /app/environment

WORKDIR /app

RUN mkdir -p /app/output /app/environment/var/object_cache \
    && chmod 0755 /app/environment/tools/rebuild_emit.sh /app/environment/tools/run_emit_chain.sh
