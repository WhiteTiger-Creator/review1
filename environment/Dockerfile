FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends tmux asciinema python3 python3-venv make binutils util-linux ca-certificates && python3 -m venv /opt/pytools && /opt/pytools/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements.txt && rm -rf /var/lib/apt/lists/* /tmp/requirements.txt

ENV PATH="/opt/pytools/bin:${PATH}"

COPY Makefile /app/Makefile
COPY src/ /app/src/
COPY --chmod=755 bin/ /app/bin/
COPY --chmod=755 harness/ /app/harness/
COPY inputs/ /app/inputs/
COPY docs/ /app/docs/
