# BASE_IMAGE_JUSTIFICATION: Julia has no canonical Harbor base image; install the
# official julialang.org linux/x64 tarball on sanctioned Debian bookworm-slim (same
# pattern as other Julia scientific tasks). Image builds offline after the pinned tarball is fetched.
FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

ENV JULIA_VERSION=1.11.5
ENV JULIA_PATH=/opt/julia
ENV JULIA_DEPOT_PATH=/opt/julia-depot
ENV JULIA_PKG_OFFLINE=true
ENV PATH="/opt/julia/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

WORKDIR /app

COPY requirements.lock /environment/requirements.lock

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tmux \
    asciinema \
    python3 \
    python3-venv \
    && curl -fL -o /tmp/julia.tar.gz \
        "https://julialang-s3.julialang.org/bin/linux/x64/1.11/julia-${JULIA_VERSION}-linux-x86_64.tar.gz" \
    && echo "723e878c642220cc0251a0e13758c059a389cadc7f01376feaf1ea7388fe8f9c  /tmp/julia.tar.gz" \
        | sha256sum --check --strict - \
    && mkdir -p /opt/julia \
    && tar -xzf /tmp/julia.tar.gz -C /opt/julia --strip-components=1 \
    && rm /tmp/julia.tar.gz \
    && julia --version \
    && rm -rf /var/lib/apt/lists/* \
    && tmux -V \
    && asciinema --version \
    && python3 -m venv /opt/verifier_venv \
    && /opt/verifier_venv/bin/pip install --no-cache-dir \
        -r /environment/requirements.lock

COPY app/ ./

RUN find /app -type f \( -name '*.jl' -o -name '*.sh' -o -name '*.toml' -o -name '*.csv' -o -name '*.md' -o -name 'pabcal' \) -exec sed -i 's/\r$//' {} + \
    && chmod +x /app/build.sh \
    && test -f /app/pabcal.jl \
    && test -f /app/src/csv_load.jl \
    && test -f /app/src/policy_load.jl \
    && test -f /app/src/compensate.jl \
    && test -f /app/src/weights.jl \
    && test -f /app/src/report_emit.jl \
    && test -f /app/config/cal_policy.toml \
    && test -f /app/data/sealed/production_policy.sha256 \
    && test -f /app/data/desk_journal.csv \
    && test -f /app/data/sample_array.csv \
    && test -f /app/docs/beamform-model.md \
    && test -f /app/docs/csv-format.md \
    && test -f /app/docs/cli-contract.md \
    && test -f /app/docs/report-schema.md \
    && test -f /app/docs/artifact-format.md \
    && test -f /app/docs/desk-derivation.md \
    && bash /app/build.sh \
    && chmod a-w /app/data/sample_array.csv /app/data/desk_journal.csv /app/data/sealed/production_policy.sha256 \
    && find /app/docs -type f -exec chmod a-w {} + \
    && /opt/verifier_venv/bin/python3 -m pytest --version

ENV PATH="/app/bin:/app:/opt/julia/bin:${PATH}"
ENV PYTHONPATH="/app"

CMD ["sleep", "infinity"]
