# ── Stage 1: FFmpeg base ──────────────────────────────────────────
FROM debian:bookworm-slim AS ffmpeg

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Python app ───────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Install ffmpeg from stage 1
COPY --from=ffmpeg /usr/bin/ffmpeg /usr/bin/ffmpeg
COPY --from=ffmpeg /usr/bin/ffprobe /usr/bin/ffprobe
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libav* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libsw* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libpostproc* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libx264* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libvpx* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libvorbis* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libvorbisenc* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libmp3lame* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libopus* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libtheora* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libva* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libdrm* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libmfx* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libnuma* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libz* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libbz2* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/liblzma* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libgcc_s* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libstdc++* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libogg* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libspeex* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libsoxr* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libgnutls* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libp11* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libtasn1* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libnettle* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libhogweed* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libgmp* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libidn2* /usr/lib/x86_64-linux-gnu/
COPY --from=ffmpeg /usr/lib/x86_64-linux-gnu/libunistring* /usr/lib/x86_64-linux-gnu/
RUN ldconfig

WORKDIR /app

# Python deps
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app/ .
COPY tikbypass.py /app/tikbypass.py

# Upload/output dirs
RUN mkdir -p /tmp/tikbypass/uploads /tmp/tikbypass/outputs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
