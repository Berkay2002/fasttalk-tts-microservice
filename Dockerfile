# CUDA-enabled base image for GPU-capable chatterbox backend
FROM fasttalk/base:cuda12.1-py310-torch260

# Set working directory
WORKDIR /app

# System dependencies are already provided by the shared base image

# Copy dependency file first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies (torch/torchaudio already baked into base)
RUN pip3 install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

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
