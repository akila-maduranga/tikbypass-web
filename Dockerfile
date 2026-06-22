FROM python:3.12-slim-bookworm

# Install ffmpeg with all dependencies properly
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

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
