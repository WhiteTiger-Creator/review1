FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c
ARG CACHEBUST=20260725100000

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        bash python3 python3-pip tmux util-linux asciinema \
 && rm -rf /var/lib/apt/lists/*

COPY wheels/ /opt/wheels/
RUN pip3 install --no-cache-dir --break-system-packages \
    --no-index --find-links /opt/wheels/ \
    pytest==8.2.2 pytest-json-ctrf==0.3.5

COPY app/ /app/

