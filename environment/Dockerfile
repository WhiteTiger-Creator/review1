FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:f3a68cf41a855d227d1b0ab832bed9749469ef38cf4f58182fb8c893bc462383

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    SOURCE_DATE_EPOCH=1704067200 \
    NODE_ENV=production \
    AURORA_FFMPEG=/usr/bin/ffmpeg

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg=7:5.1.9-0+deb12u1 make=4.3-4.1 tmux=3.3a-3 asciinema=2.2.0-1 python3=3.11.2-1+b1 python3-pip=23.0.1+dfsg-1 file=1:5.44-3 bash=5.2.15-2+b13 patch=2.7.6-7 ca-certificates=20230311+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

COPY verifier-requirements.txt /tmp/verifier-requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages \
      -r /tmp/verifier-requirements.txt
RUN rm -f /tmp/verifier-requirements.txt

COPY app/package.json app/package-lock.json /app/
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund

COPY app/ /app/
COPY data/ /data/
COPY refresh_inventory_digests.py /tmp/refresh_inventory_digests.py

# Generate tiny deterministic media fixtures and refresh inventory digests.
RUN set -eux; \
    mkdir -p "/data/assets/clips" "/data/assets/subtitles"; \
    ffmpeg -hide_banner -loglevel error -y \
      -f lavfi -i color=c=blue:s=320x240:d=1 -f lavfi -i sine=frequency=440:duration=1 \
      -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \
      "/data/assets/clips/interview-sdr.mp4"; \
    ffmpeg -hide_banner -loglevel error -y \
      -f lavfi -i testsrc2=s=640x360:d=1 -f lavfi -i sine=frequency=880:duration=1 \
      -fflags +bitexact -map_metadata -1 \
      -c:v libx264 -flags:v +bitexact -pix_fmt yuv420p10le -color_trc smpte2084 \
      -c:a aac -flags:a +bitexact -shortest -write_crc32 0 \
      "/data/assets/clips/launch master #1.mkv"; \
    ffmpeg -hide_banner -loglevel error -y \
      -f lavfi -i "color=c=green:s=320x240:d=1,format=rgba" \
      -f lavfi -i sine=frequency=220:duration=1 \
      -c:v qtrle -c:a pcm_s16le -shortest \
      /tmp/alpha-clip.mov; \
    python3 -c 'import shutil; shutil.move("/tmp/alpha-clip.mov", "/data/assets/clips/alpha-dollar$.mov")'; \
    printf '1\n00:00:00,000 --> 00:00:01,000\nLaunch EN\n' > "/data/assets/subtitles/launch master #1.en.srt"; \
    printf '1\n00:00:00,000 --> 00:00:01,000\nLaunch FR\n' > "/data/assets/subtitles/launch master #1.fr.srt"; \
    printf '1\n00:00:00,000 --> 00:00:01,000\nInterview EN\n' > "/data/assets/subtitles/interview-sdr.en.srt"; \
    python3 /tmp/refresh_inventory_digests.py; \
    rm /tmp/refresh_inventory_digests.py

RUN mkdir -p /output /logs/verifier /logs/agent \
    && chown -R root:root /data /app/docs /app/schemas /app/config \
    && chmod -R a-w /data /app/docs /app/schemas /app/config \
    && chmod +x /app/aurora-build.mjs

CMD ["sleep", "infinity"]
