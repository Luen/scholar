# Use Python base image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Google credentials file
COPY google-credentials.json .

# Expose the port for Flask application
EXPOSE 5000

# Define the command to run the Flask app
CMD ["python", "main.py"]
