# PDF Composer Worker Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY workers/composer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY workers/composer/main.py ./workers/composer/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Run worker
CMD ["uvicorn", "workers.composer.main:app", "--host", "0.0.0.0", "--port", "8080"]
