# Use specific version for reproducibility
FROM python:3.10.13-slim-bullseye AS base

# Install only necessary system dependencies
RUN apt-get update && apt-get install -y \
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

# Create a non-root user
RUN useradd -m -s /bin/bash app_user

# Set the working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install dependencies with verbosity
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -v -r requirements.txt && \
    pip list

# Create necessary directories
RUN mkdir -p /app/scholar_data /app/cache /var/log \
    && chown -R app_user:app_user /app /var/log
