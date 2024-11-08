# Use Python base image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy all files from the current directory to the container's working directory
COPY . .

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Add a new cron job to run main.py every two weeks
RUN echo "0 0 */14 * * python /app/main.py ynWS968AAAAJ >> /var/log/cron.log 2>&1" > /etc/cron.d/run_main

# Apply permissions to the cron job file
RUN chmod 0644 /etc/cron.d/run_main && crontab /etc/cron.d/run_main

# Expose the port for Flask application
EXPOSE 5000

# Start cron and keep container running
CMD ["bash", "-c", "cron && tail -f /var/log/cron.log"]