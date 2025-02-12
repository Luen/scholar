# Use Python base image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    cron \
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

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create script, set up directories and cron
RUN echo '#!/bin/bash\nsudo service cron start\npython serve.py' > /app/start.sh \
    && mkdir -p /app/scholar_data /app/html_cache /var/log \
    && touch /var/log/cron.log \
    && chmod +x /app/start.sh \
    && chown -R app_user:app_user /app /var/log/cron.log \
    && echo "0 0 */14 * * cd /app && python main.py ynWS968AAAAJ >> /var/log/cron.log 2>&1" > /etc/cron.d/run_main \
    && chmod 0644 /etc/cron.d/run_main \
    && crontab -u app_user /etc/cron.d/run_main

# Switch to non-root user
USER app_user

# Expose the port for Flask application
EXPOSE 5000

# Start the Flask server with proper shell execution
CMD ["/bin/bash", "/app/start.sh"]