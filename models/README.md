# TTS Models Directory

This directory is mounted as a volume in the Docker container for the TTS service.

## Purpose

Place any pre-trained TTS model files here that the service needs to access. The docker-compose.yml mounts this directory to `/app/models` inside the container.

## Usage

If your TTS service requires model files (like ONNX models, checkpoints, etc.), place them in this directory before starting the containers.

If the TTS service downloads models automatically at runtime, this directory will be used as the model cache.

## Notes

- This directory can be empty if the TTS service downloads models on first run
- Check the TTS service documentation for specific model requirements
- Large model files should not be committed to git (add to .gitignore)
