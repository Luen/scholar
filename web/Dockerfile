# Build from base image
FROM scholar-base:latest

# Copy application code
COPY --chown=app_user:app_user . .

# Switch to non-root user
USER app_user

# Expose the port for Flask application
EXPOSE 5000

# Start the Flask server
CMD ["python", "server.py"]
