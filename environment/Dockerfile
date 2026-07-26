FROM debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
  r-base=4.2.2.20221110-2 \
  r-base-dev=4.2.2.20221110-2 \
  python3=3.11.2-1+b1 \
  python3-pip=23.0.1+dfsg-1 \
  python3-venv=3.11.2-1+b1 \
  tmux=3.3a-3 \
  asciinema=2.2.0-1 \
  ca-certificates=20230311+deb12u1 \
  && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier
COPY requirements.txt /tmp/requirements.txt
RUN /opt/verifier/bin/pip install --require-hashes --no-deps -r /tmp/requirements.txt
RUN ln -sf /opt/verifier/bin/pytest /usr/local/bin/pytest
ENV PATH=/opt/verifier/bin:${PATH}

COPY docs/ /app/environment/docs/
COPY fc2/ /app/environment/fc2/
COPY fixtures/ /app/environment/fixtures/
COPY lib/ /app/environment/lib/
COPY migrations/ /app/environment/migrations/
COPY profiles/ /app/environment/profiles/
COPY rk4/ /app/environment/rk4/
COPY rp3/ /app/environment/rp3/
COPY scripts/ /app/environment/scripts/
COPY tools/ /app/environment/tools/
COPY ws7/ /app/environment/ws7/
RUN chmod +x /app/environment/scripts/*.sh /app/environment/migrations/*.sh \
  && Rscript -e 'dir.create("/app/environment/r_libs", showWarnings=FALSE); .libPaths(c("/app/environment/r_libs", .libPaths())); install.packages("jsonlite", lib="/app/environment/r_libs", repos="https://cloud.r-project.org")'

ENV R_LIBS_USER=/app/environment/r_libs

CMD ["bash", "-lc", "echo Environment ready"]
