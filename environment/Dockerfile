FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake=3.25.1-1 \
    make=4.3-4.1 \
    patch=2.7.6-7 \
    openmpi-bin=4.1.4-3+b1 \
    libopenmpi-dev=4.1.4-3+b1 \
    libhdf5-dev=1.10.8+repack1-1 \
    libhdf5-openmpi-dev=1.10.8+repack1-1 \
    hdf5-tools=1.10.8+repack1-1 \
    python3=3.11.2-1+b1 \
    python3-pip=23.0.1+dfsg-1 \
    python3-h5py=3.7.0-8 \
    python3-numpy=1:1.24.2-1+deb12u1 \
    tmux=3.3a-3 \
    asciinema=2.2.0-1 \
    ca-certificates=20230311+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

ENV HDF5_ROOT=/usr/lib/x86_64-linux-gnu/hdf5/openmpi
ENV OMPI_ALLOW_RUN_AS_ROOT=1
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

COPY CMakeLists.txt /app/environment/CMakeLists.txt
COPY README.md /app/environment/README.md
COPY .dockerignore /app/environment/.dockerignore
COPY core /app/environment/core
COPY storage /app/environment/storage
COPY restart /app/environment/restart
COPY numerics /app/environment/numerics
COPY docs /app/environment/docs
COPY cfg_store /app/environment/cfg_store
COPY profiles /app/environment/profiles
COPY scripts /app/environment/scripts
COPY h1 /app/environment/h1
COPY tools /app/environment/tools
COPY migrations /app/environment/migrations
COPY fixtures /app/environment/fixtures

RUN chmod +x \
      /app/environment/h1/run_x7.sh \
      /app/environment/tools/x7_gate \
      /app/environment/scripts/build_x7.sh \
      /app/environment/scripts/seed_ckpts.sh \
      /app/environment/migrations/purge_x7.sh \
    && bash /app/environment/scripts/build_x7.sh \
    && bash /app/environment/scripts/seed_ckpts.sh \
    && mkdir -p /app/output/stage /logs/verifier
