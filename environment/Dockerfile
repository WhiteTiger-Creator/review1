FROM public.ecr.aws/docker/library/debian:bookworm-slim@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d

RUN apt-get update && apt-get install -y --no-install-recommends \
        r-base-core \
        r-cran-survival \
        r-cran-jsonlite \
        python3 \
        python3-pip \
        tmux \
        asciinema \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
        pytest==8.2.0 \
        pytest-json-ctrf==0.3.5 \
        numpy==2.2.6

WORKDIR /app

COPY data/ /app/data/
COPY docs/ /app/docs/
COPY R/ /app/R/
COPY DESCRIPTION /app/DESCRIPTION
COPY analysis.R /app/analysis.R
