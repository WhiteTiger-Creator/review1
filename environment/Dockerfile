FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        g++ \
        cmake \
        make \
        ca-certificates \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

# Run the agent session as a restricted, non-root user (task.toml sets
# [agent].user = "agent"). There is no USER directive, so the image build and
# the verifier still run as root: the verifier can write /logs/verifier and
# keeps /opt/fixed and the Python interpreter root-owned, so a session cannot
# rewrite the frozen sources or the verifier to pass without solving the task.
RUN useradd --create-home --shell /bin/bash agent

WORKDIR /app/environment

COPY requirements.lock /app/environment/requirements.lock
RUN python3 -m venv /opt/test-venv \
    && /opt/test-venv/bin/pip install --no-cache-dir --require-hashes -r /app/environment/requirements.lock

COPY CMakeLists.txt README.md build.sh /app/environment/
COPY data/ /app/environment/data/
COPY include/ /app/environment/include/
COPY src/ /app/environment/src/
COPY docs/ /app/environment/docs/

RUN chmod +x build.sh

# Pristine, root-owned copy of the fixed sources and headers the agent cannot
# edit. The verifier compiles from these plus the agent's src/matsqrt_impl.cpp,
# so only src/matsqrt_impl.cpp can influence the graded behavior.
RUN mkdir -p /opt/fixed \
    && cp include/matsqrt.hpp include/mat_io.hpp src/main.cpp /opt/fixed/

# Give the agent ownership of exactly what it edits and builds in: the source
# directory, the implementation file, and the environment directory (so it can
# create build/). /opt/fixed, the interpreter, and the other sources stay
# root-owned and read-only to the agent.
RUN chown agent:agent /app/environment /app/environment/src /app/environment/src/matsqrt_impl.cpp

WORKDIR /app/environment
