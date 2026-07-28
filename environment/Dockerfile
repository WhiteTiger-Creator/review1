FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c AS arena-builder

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      make \
      patch \
      python3 \
      python3-pip \
      python3-venv && \
    rm -rf /var/lib/apt/lists/*

COPY vendor/arena-vendor.tar.gz vendor/SHA256SUMS vendor/PROVENANCE.md /opt/arena-vendor/
RUN cd /opt/arena-vendor && \
    sha256sum -c SHA256SUMS && \
    mkdir -p /opt/arena-assets && \
    tar --no-same-owner -xzf /opt/arena-vendor/arena-vendor.tar.gz \
      -C /opt/arena-assets && \
    rm -f /opt/arena-vendor/arena-vendor.tar.gz

RUN mkdir -p /opt/verifier-vendor && \
    cp /opt/arena-assets/wheels/wheelhouse.tar.gz \
      /opt/arena-assets/wheels/SHA256SUMS \
      /opt/arena-assets/wheels/PROVENANCE.md \
      /opt/verifier-vendor/ && \
    cd /opt/verifier-vendor && \
    sha256sum -c SHA256SUMS && \
    mkdir -p /opt/arena-wheels && \
    tar --no-same-owner -xzf wheelhouse.tar.gz -C /opt/arena-wheels && \
    rm -f wheelhouse.tar.gz && \
    python3 -m venv /opt/arena-venv && \
    /opt/arena-venv/bin/pip install \
      --no-cache-dir \
      --no-index \
      --find-links=/opt/arena-wheels \
      --require-hashes \
      -r /opt/arena-wheels/requirements.txt && \
    /opt/arena-venv/bin/pip check && \
    /opt/arena-venv/bin/python -m pytest --version >/dev/null

WORKDIR /build

RUN mkdir -p /build/engine-package /build/native-package && \
    cp /opt/arena-assets/engine/fairy-stockfish-vendor.tar.gz \
      /opt/arena-assets/engine/SHA256SUMS \
      /opt/arena-assets/engine/PROVENANCE.md \
      /build/engine-package/ && \
    cp /opt/arena-assets/native/arena_sources.tar.gz \
      /opt/arena-assets/native/SHA256SUMS \
      /opt/arena-assets/native/PROVENANCE.md \
      /build/native-package/

RUN cd /build/engine-package && \
    sha256sum -c SHA256SUMS && \
    mkdir -p /build/engine-vendor && \
    tar --no-same-owner -xzf fairy-stockfish-vendor.tar.gz \
      -C /build/engine-vendor && \
    rm -f fairy-stockfish-vendor.tar.gz && \
    cd /build/engine-vendor && \
    sha256sum -c SHA256SUMS && \
    mkdir -p /build/fairy-stockfish /build/notices/fairy-stockfish && \
    tar --no-same-owner -xzf fairy_sf_14.tar.gz --strip-components=1 \
      -C /build/fairy-stockfish && \
    patch --batch --forward -d /build/fairy-stockfish -p1 \
      < timeman-identifier.patch && \
    cp Copying.txt AUTHORS PROVENANCE.md /build/notices/fairy-stockfish/ && \
    cd /build/native-package && \
    sha256sum -c SHA256SUMS && \
    mkdir -p /build/native /build/notices/arena-native && \
    tar --no-same-owner -xzf arena_sources.tar.gz -C /build/native && \
    cp PROVENANCE.md /build/notices/arena-native/ && \
    mkdir -p /out

RUN case "$(uname -m)" in \
      x86_64|amd64) fairy_arch=general-64 ;; \
      aarch64|arm64) fairy_arch=armv8 ;; \
      *) \
        printf 'Unsupported build architecture: %s\n' "$(uname -m)" >&2; \
        exit 1 \
        ;; \
    esac && \
    make -C /build/fairy-stockfish/src -j1 build \
      ARCH="$fairy_arch" nnue=no optimize=no largeboards=yes all=yes \
      EXTRACXXFLAGS='-O2' && \
    install -D -m 0700 /build/fairy-stockfish/src/stockfish /out/opponent

RUN case "$(uname -m)" in \
      x86_64|amd64) fairy_defs='-DLARGEBOARDS -DPRECOMPUTED_MAGICS -DALLVARS -DIS_64BIT -DNO_PREFETCH' ;; \
      aarch64|arm64) fairy_defs='-DLARGEBOARDS -DPRECOMPUTED_MAGICS -DALLVARS -DIS_64BIT -DUSE_POPCNT -DUSE_NEON' ;; \
      *) \
        printf 'Unsupported build architecture: %s\n' "$(uname -m)" >&2; \
        exit 1 \
        ;; \
    esac && \
    g++ -std=c++20 -O2 -DNDEBUG -Wall -Wextra -Werror \
      -Wno-deprecated-enum-enum-conversion \
      -DNNUE_EMBEDDING_OFF -DUSE_PTHREADS $fairy_defs \
      -I/build/fairy-stockfish/src -I/build/native/server \
      /build/native/server/*.cpp \
      /build/fairy-stockfish/src/benchmark.o \
      /build/fairy-stockfish/src/bitbase.o \
      /build/fairy-stockfish/src/bitboard.o \
      /build/fairy-stockfish/src/endgame.o \
      /build/fairy-stockfish/src/evaluate.o \
      /build/fairy-stockfish/src/material.o \
      /build/fairy-stockfish/src/misc.o \
      /build/fairy-stockfish/src/movegen.o \
      /build/fairy-stockfish/src/movepick.o \
      /build/fairy-stockfish/src/pawns.o \
      /build/fairy-stockfish/src/position.o \
      /build/fairy-stockfish/src/psqt.o \
      /build/fairy-stockfish/src/search.o \
      /build/fairy-stockfish/src/thread.o \
      /build/fairy-stockfish/src/timeman.o \
      /build/fairy-stockfish/src/tt.o \
      /build/fairy-stockfish/src/uci.o \
      /build/fairy-stockfish/src/ucioption.o \
      /build/fairy-stockfish/src/tune.o \
      /build/fairy-stockfish/src/tbprobe.o \
      /build/fairy-stockfish/src/evaluate_nnue.o \
      /build/fairy-stockfish/src/half_ka_v2.o \
      /build/fairy-stockfish/src/partner.o \
      /build/fairy-stockfish/src/parser.o \
      /build/fairy-stockfish/src/piece.o \
      /build/fairy-stockfish/src/variant.o \
      /build/fairy-stockfish/src/xboard.o \
      /build/fairy-stockfish/src/half_ka_v2_variants.o \
      -lpthread -o /out/referee

RUN g++ -std=c++20 -O2 -DNDEBUG -Wall -Wextra -Werror -Wpedantic \
      -I/build/native/client /build/native/client/*.cpp -o /out/arena

RUN { \
      printf 'uci\nsetoption name UCI_Variant value kyotoshogi\nsetoption name Threads value 1\nsetoption name Hash value 16\nsetoption name Ponder value false\nsetoption name Use NNUE value false\nsetoption name Skill Level value 20\nsetoption name MultiPV value 3\nisready\nposition startpos\ngo nodes 32\n'; \
      sleep 1; \
      printf 'quit\n'; \
    } | /out/opponent >/tmp/opponent-smoke.txt 2>&1 && \
    grep -q 'option name UCI_Variant .* var kyotoshogi' /tmp/opponent-smoke.txt && \
    grep -q '^uciok$' /tmp/opponent-smoke.txt && \
    grep -q '^readyok$' /tmp/opponent-smoke.txt && \
    grep -q '^bestmove ' /tmp/opponent-smoke.txt && \
    rm -f /tmp/opponent-smoke.txt && \
    strip /out/arena /out/referee /out/opponent


FROM public.ecr.aws/docker/library/gcc:13-bookworm@sha256:930f2ebe239275fa67226654cb79273ea34eee672ae61c8a39f689c37fb7ac5c

LABEL org.opencontainers.image.title="Kyoto Shogi arena" \
      org.opencontainers.image.description="Playable board-game arena for a Kyoto Shogi match" \
      org.opencontainers.image.source="https://example.invalid/kyoto-shogi-arena" \
      org.opencontainers.image.revision="12" \
      org.opencontainers.image.created="2026-07-21T00:00:00Z" \
      org.opencontainers.image.version="1.0.11" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/tmp \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TMPDIR=/tmp

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      asciinema \
      make \
      patch \
      python3 \
      tmux && \
    rm -rf /var/lib/apt/lists/*

COPY app/ /app/
COPY --from=arena-builder /opt/arena-venv/ /opt/arena-venv/
COPY --from=arena-builder /out/arena /app/arena
COPY --from=arena-builder /out/referee /opt/arena-private/referee
COPY --from=arena-builder /out/opponent /opt/arena-private/opponent
COPY --from=arena-builder --chmod=0700 /build/notices/ /usr/share/doc/kyoto-shogi-arena/
COPY OPPONENT_POLICY.md /usr/share/doc/kyoto-shogi-arena/OPPONENT_POLICY.md
COPY arena/difficulty_knobs.conf /opt/arena-private/difficulty_knobs.conf
COPY --from=arena-builder /opt/arena-assets/arena/healthcheck.sh /opt/arena-private/healthcheck.sh
COPY --from=arena-builder /opt/arena-assets/arena/bootstrap.sh /usr/local/sbin/arena-bootstrap

RUN chmod 0755 /app/arena && \
    command -v g++ >/dev/null && \
    command -v make >/dev/null && \
    command -v python3 >/dev/null && \
    test -x /opt/arena-venv/bin/python && \
    test -r /usr/share/doc/kyoto-shogi-arena/fairy-stockfish/Copying.txt && \
    test -r /usr/share/doc/kyoto-shogi-arena/fairy-stockfish/PROVENANCE.md && \
    test -r /usr/share/doc/kyoto-shogi-arena/arena-native/PROVENANCE.md && \
    chmod 0700 /opt/arena-private /opt/arena-venv \
      /opt/arena-private/referee \
      /opt/arena-private/opponent \
      /opt/arena-private/healthcheck.sh \
      /usr/local/sbin/arena-bootstrap && \
    chmod 0600 /opt/arena-private/difficulty_knobs.conf && \
    install -d -m 0755 /run/arena && \
    install -d -m 1777 /logs

HEALTHCHECK --interval=1s --timeout=3s --start-period=1s --retries=30 \
    CMD ["/opt/arena-private/healthcheck.sh"]

ENTRYPOINT ["/usr/local/sbin/arena-bootstrap"]
