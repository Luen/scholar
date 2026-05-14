# Build from base image
FROM scholar-base:latest

# Copy application code
COPY --chown=app_user:app_user . .

# Switch to non-root user
USER app_user

# Expose the port for Flask application
EXPOSE 5000

# Production WSGI (avoids Flask's built-in dev server warning and is suitable behind Docker)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "server:app"]
