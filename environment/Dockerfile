FROM public.ecr.aws/docker/library/ubuntu:24.04@sha256:0d39fcc8335d6d74d5502f6df2d30119ff4790ebbb60b364818d5112d9e3e932

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        make \
        openjdk-17-jdk-headless \
        python3 \
        python3-venv \
        tmux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

ENV PATH="/opt/verifier/bin:${PATH}"
WORKDIR /app

COPY app/Makefile /app/Makefile
COPY app/bin/ /app/bin/
COPY app/lib/ /app/lib/
COPY app/tablebook/ /app/tablebook/
COPY app/examples/ /app/examples/
COPY app/src/ /app/src/

RUN java -version \
    && javac -version \
    && make -C /app compile-check \
    && make -C /app starter-check

CMD ["/bin/bash"]
