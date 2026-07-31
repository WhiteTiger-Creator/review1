FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        tmux \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir \
        pytest==8.3.4 \
        pytest-json-ctrf==0.3.5

# What the packaging team publishes about DPX/1.
COPY docs/ /usr/local/share/doc/dpx/

# The package tool. Inspection plus the --force repair hatch; transactions themselves are
# driven by the fleet orchestrator, which does not run on the boxes.
COPY dpx /usr/local/sbin/dpx
RUN chmod 0755 /usr/local/sbin/dpx

# The machine as it came back up: package database, journals, cached archives and the
# file tree the interrupted run left behind. File modes carry over from the context, so
# the staged leftovers arrive with the mode staging gave them.
COPY root/ /

# One of the files the run had staged is a symlink, and the file it points at was staged
# too and never committed, so the link has nothing to resolve to yet. It is made here
# rather than carried in the build context, which has no business holding a broken link.
RUN ln -s libnet.so.1.5 /usr/lib/netcfg/libnet.so.1.dpx-part

WORKDIR /var/lib/dpx
