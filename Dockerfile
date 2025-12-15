FROM nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.10 and system dependencies (matching main app)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-dev \
    python3.10-venv \
    build-essential \
    libsndfile1 \
    libportaudio2 \
    ffmpeg \
    portaudio19-dev \
    git \
    wget \
    python3-setuptools \
    python3.10-distutils \
    ninja-build \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 the default python/pip
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy project files
COPY . /app

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
