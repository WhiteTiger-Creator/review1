FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c

ENV TZ=UTC \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    CMAKE_BUILD_PARALLEL_LEVEL=2 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends python3=3.11.2-1+b1 python3-pytest=7.2.1-2 python3-numpy=1:1.24.2-1+deb12u1 python3-scipy=1.10.1-2 python3-jsonschema=4.10.3-1 \
    cmake=3.25.1-1 \
    ninja-build=1.11.1-2~deb12u1 \
    libeigen3-dev=3.4.0-4 \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    jq=1.6-2.1+deb12u2 \
    file=1:5.44-3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY CMakeLists.txt /app/CMakeLists.txt
COPY cmake /app/cmake
COPY emsolve /app/emsolve
COPY data /app/data
COPY docs /app/docs
COPY scripts /app/scripts

RUN chmod +x /app/scripts/*.sh \
    && mkdir -p /app/build /app/bin /app/checkpoints /app/data/checkpoints /output /logs/emsolve /logs/verifier /logs/agent

CMD ["sleep", "infinity"]
