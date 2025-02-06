# Use Python base image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    cron \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash app_user

# Set the working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers
RUN playwright install chromium

# Copy the rest of the application
COPY . .

# Create necessary directories with correct permissions
RUN mkdir -p /app/scholar_data /app/html_cache /var/log \
    && touch /var/log/cron.log \
    && chown -R app_user:app_user /app /var/log/cron.log

# Add cron job to run main.py every two weeks
RUN echo "0 0 */14 * * cd /app && python main.py ynWS968AAAAJ >> /var/log/cron.log 2>&1" > /etc/cron.d/run_main \
    && chmod 0644 /etc/cron.d/run_main \
    && crontab -u app_user /etc/cron.d/run_main

# Switch to non-root user
USER app_user

# Expose the port for Flask application
EXPOSE 5000

# Create a script to run both cron and Flask
COPY <<EOF /app/start.sh
#!/bin/bash
sudo service cron start
python serve.py
EOF

RUN chmod +x /app/start.sh

# Start both cron and Flask
CMD ["/app/start.sh"]