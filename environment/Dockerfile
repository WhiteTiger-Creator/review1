FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

# The sanctioned Python base supplies the verifier runtime; pinned Debian
# snapshot packages add the required R runtime.
RUN printf '%s\n' \
      'Types: deb' \
      'URIs: http://snapshot.debian.org/archive/debian/20260316T000000Z' \
      'Suites: bookworm bookworm-updates' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
      '' \
      'Types: deb' \
      'URIs: http://snapshot.debian.org/archive/debian-security/20260316T000000Z' \
      'Suites: bookworm-security' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
      > /etc/apt/sources.list.d/debian.sources && \
    printf '%s\n' 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99snapshot && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends \
      tmux=3.3a-3 \
      asciinema=2.2.0-1 \
      strace=6.1-0.1 \
      libgomp1=12.2.0-14+deb12u1 \
      ca-certificates=20230311+deb12u1 \
      r-base-core=4.2.2.20221110-2 \
      r-recommended=4.2.2.20221110-2 \
      r-cran-jsonlite=1.8.4+dfsg-1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt

WORKDIR /app
RUN useradd --create-home --shell /bin/bash candidate && \
    mkdir -p /app/data /app/outputs /app/contracts /opt/original_data

COPY data/ /app/data/
COPY contracts/ /app/contracts/
COPY analysis.R /app/analysis.R

RUN cp /app/data/train.csv /opt/original_data/train.csv && \
    cp /app/data/score.csv /opt/original_data/score.csv && \
    chown -R root:root /app/data /app/contracts /opt/original_data && \
    find /app/data /app/contracts /opt/original_data -type d -exec chmod 0555 {} + && \
    find /app/data /app/contracts /opt/original_data -type f -exec chmod 0444 {} + && \
    chown candidate:candidate /app/analysis.R /app/outputs && \
    chmod 0644 /app/analysis.R && \
    chmod 0755 /app/outputs
