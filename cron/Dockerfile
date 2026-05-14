# Build from base image
FROM scholar-base:latest

# Install cron and sudo
RUN apt-get update && apt-get install -y \
    cron \
    sudo \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/crond \
    && chown -R app_user:app_user /var/run/crond \
    && echo "app_user ALL=(ALL) NOPASSWD: /usr/sbin/cron" >> /etc/sudoers

# Copy application code
COPY --chown=app_user:app_user . .

# Setup cron job and logs directory
RUN touch /var/log/app.log \
    && chown app_user:app_user /var/log/app.log \
    && mkdir -p /app/logs \
    && chown -R app_user:app_user /app/logs \
    && printf '%s\n%s\n%s\n%s\n' \
        "0 0 */14 * * cd /app && python -u main.py ynWS968AAAAJ >> /var/log/app.log 2>&1 && python -u main.py g9B1IoQAAAAJ >> /var/log/app.log 2>&1 && python -u main.py cXDRggIAAAAJ >> /var/log/app.log 2>&1" \
        "0 2 * * * cd /app && python -u scripts/revalidate_doi_metrics.py >> /var/log/app.log 2>&1" \
        "0 5 * * * cd /app && python -u main.py ynWS968AAAAJ --refresh-news >> /var/log/app.log 2>&1 && python -u main.py g9B1IoQAAAAJ --refresh-news >> /var/log/app.log 2>&1 && python -u main.py cXDRggIAAAAJ --refresh-news >> /var/log/app.log 2>&1" \
        "0 12 * * * cd /app && python -u main.py ynWS968AAAAJ --bake-media-filtered >> /var/log/app.log 2>&1 && python -u main.py g9B1IoQAAAAJ --bake-media-filtered >> /var/log/app.log 2>&1 && python -u main.py cXDRggIAAAAJ --bake-media-filtered >> /var/log/app.log 2>&1" \
        > /etc/cron.d/scholar_cron \
    && chmod 0644 /etc/cron.d/scholar_cron \
    && crontab -u app_user /etc/cron.d/scholar_cron

# Create a wrapper script to run cron
RUN echo '#!/bin/bash\nsudo /usr/sbin/cron -f' > /app/start-cron.sh \
    && chmod +x /app/start-cron.sh

# Switch to non-root user
USER app_user

# Start cron in foreground using the wrapper
CMD ["/app/start-cron.sh"]
