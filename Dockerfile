FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libsndfile1 \
    libportaudio2 \
    ffmpeg \
    git \
    wget \
 && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Ensure output directory exists for generated audio files
RUN mkdir -p /app/output

# Default environment variables
ENV TTS_HOST=0.0.0.0 \
    TTS_PORT=8000 \
    TTS_MONITORING_HOST=0.0.0.0 \
    TTS_MONITORING_PORT=9093

# Expose service and monitoring ports
EXPOSE 8000 9093

# Default command: run in WebSocket server mode
CMD ["python", "-u", "main.py", "websocket"]
