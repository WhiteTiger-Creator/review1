# Canonical Ubuntu 24.04 final-stage digest (docs/CANONICAL_BASE_IMAGES.md /
# config/platform_policy.toml). Used as the C/build-essential runtime base;
# no language-specific t-bench image is required for this task.
FROM public.ecr.aws/docker/library/ubuntu:24.04@sha256:0d39fcc8335d6d74d5502f6df2d30119ff4790ebbb60b364818d5112d9e3e932

ENV DEBIAN_FRONTEND=noninteractive
ENV TERM=xterm
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TMUX_TMPDIR=/var/tmp/tmux

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential make python3 python3-venv asciinema ca-certificates ncurses-term tmux \
&& mkdir -p /var/tmp/tmux \
    && chmod 1777 /var/tmp/tmux \
    && rm -rf /var/lib/apt/lists/*

COPY runtime/tmux.conf /etc/tmux.conf
COPY runtime/install_verifier_deps.sh /usr/local/bin/install_verifier_deps.sh
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier-venv \
    && chmod +x /usr/local/bin/install_verifier_deps.sh \
    && /usr/local/bin/install_verifier_deps.sh /opt/verifier-venv/bin/pip /tmp/requirements.lock

COPY . /app/environment/

RUN make -C /app/environment clean all
