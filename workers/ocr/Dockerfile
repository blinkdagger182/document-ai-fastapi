# OCR Worker Dockerfile
FROM python:3.11-slim

# Install system dependencies for OpenCV and PaddleOCR
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    g++ \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY workers/ocr/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY workers/ocr/main.py ./workers/ocr/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Run worker
CMD ["python", "workers/ocr/main.py"]
