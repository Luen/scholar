# Build from base image
FROM scholar-base:latest

# Ensure gunicorn is available in this image even if `scholar-base:latest` was built from an
# older requirements.txt (e.g. compose built web before base finished). `pip` is a no-op when
# already satisfied. Use `python -m gunicorn` so we do not rely on the script being on PATH.
RUN pip install --no-cache-dir "gunicorn>=23.0.0"

# Copy application code
COPY --chown=app_user:app_user . .

# Switch to non-root user
USER app_user

# Expose the port for Flask application
EXPOSE 5000

# Production WSGI (avoids Flask's built-in dev server warning and is suitable behind Docker)
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "server:app"]
