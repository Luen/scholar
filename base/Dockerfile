# syntax=docker/dockerfile:1
# Shared runtime for web + cron: Chromium/scrapling needs Debian slim (not Alpine).
# Compose tags this as scholar-base:latest before building web/cron.
FROM python:3.10.13-slim-bullseye@sha256:e89739e9b11753ace337116c9086c4ba780c0c3daff118a7c680783cf7afada1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl: compose web healthcheck. Chromium + driver: scrapling/browser fetches.
# Explicit GTK/NSS libs kept for headless stability on bullseye.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        chromium \
        chromium-driver \
        libgconf-2-4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libgdk-pixbuf2.0-0 \
        libgtk-3-0 \
        libnss3 \
        libxss1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

# -l avoids oversized sparse lastlog files with high UIDs
RUN useradd -l -m -s /bin/bash app_user

WORKDIR /app

COPY requirements.txt .

# Skip lint/test tools in runtime images (still listed in requirements.txt for local/CI)
RUN python -m pip install --upgrade pip \
    && grep -vE '^(ruff|pytest)([<>=!~].*)?$' requirements.txt > /tmp/requirements.prod.txt \
    && pip install --no-cache-dir -r /tmp/requirements.prod.txt \
    && rm -f /tmp/requirements.prod.txt

RUN mkdir -p /app/scholar_data /app/cache /var/log \
    && chown -R app_user:app_user /app /var/log

# Compose `base` service uses command: ['true']; keep a harmless default.
CMD ["true"]
