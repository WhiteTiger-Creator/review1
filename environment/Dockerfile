FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates g++ make tmux asciinema && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock
WORKDIR /app
COPY --chmod=0777 app/ /app/
# The book is written under /app/src and built into /app/build, so both have
# to be writable by whoever is doing the work, root or not. The mode is set as
# the tree is copied rather than by a recursive chmod afterwards.
RUN mkdir -p /app/output /app/build && chmod 0777 /app/output /app/build
CMD ["/bin/bash"]
