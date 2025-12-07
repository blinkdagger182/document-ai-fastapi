# CommonForms Worker Dockerfile
# Requires Python 3.10+ for CommonForms
FROM python:3.11-slim

# Install system dependencies (including git for pip install from GitHub)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    g++ \
    git \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY workers/cf/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY workers/cf_worker.py ./workers/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8081

# Run worker
CMD ["python", "workers/cf_worker.py"]
