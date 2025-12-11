# CUDA-enabled base image for GPU-capable chatterbox backend
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    build-essential \
    libsndfile1 \
    libportaudio2 \
    ffmpeg \
    git \
    wget \
 && rm -rf /var/lib/apt/lists/*

# Copy dependency file first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies (without torch to allow GPU wheels)
RUN pip3 install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt && \
    pip3 install --no-cache-dir torch==2.6.0 torchaudio==2.6.0 --extra-index-url https://download.pytorch.org/whl/cu121

# Copy the full project
COPY . /app

# Ensure output directory exists for generated audio files
RUN mkdir -p /app/output

# Make chatterbox sources importable
ENV PYTHONPATH=/app/chatterbox/src:${PYTHONPATH:-}

# Default environment variables
ENV TTS_HOST=0.0.0.0 \
    TTS_PORT=8000 \
    TTS_MONITORING_HOST=0.0.0.0 \
    TTS_MONITORING_PORT=9093 \
    TTS_BACKEND=kokoro

# Expose service and monitoring ports
EXPOSE 8000 9093

# Default command: run in WebSocket server mode
CMD ["python3", "-u", "main.py", "websocket"]
