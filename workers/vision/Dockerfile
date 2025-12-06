FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY workers/vision/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY workers/ ./workers/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Run the worker
CMD ["python", "workers/vision/main.py"]
