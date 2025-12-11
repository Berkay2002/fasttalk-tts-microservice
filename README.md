# FastTalk TTS Microservice

GPU-enabled Chatterbox TTS and CPU-friendly Kokoro TTS behind a single WebSocket API. Select the backend with an environment variable so orchestration can choose between light CPU workloads or high-quality GPU synthesis.

## Quick start (Docker)

### Build

```bash
docker build -t fasttalk-tts .
```

### Run with Kokoro (CPU default)

```bash
docker run -it --rm \
	-p 8000:8000 -p 9093:9093 \
	-v "$PWD/output:/app/output" \
	fasttalk-tts
```

### Run with Chatterbox (GPU)

```bash
docker run --gpus all -it --rm \
	-e TTS_BACKEND=chatterbox \
	-e TTS_CHATTERBOX_DEVICE=cuda \
	-p 8000:8000 -p 9093:9093 \
	-v "$PWD/output:/app/output" \
	fasttalk-tts
```

The container prints whether CUDA is available when Chatterbox loads. If a GPU is not available, set `TTS_CHATTERBOX_DEVICE=cpu` (performance will be slower).

## WebSocket API

Connect to `ws://<host>:8000` and send JSON:

```json
{
	"text": "Hello from FastTalk!",
	"lang": "en-us",   // optional
	"voice": "af_sarah", // optional (kokoro only)
	"speed": 1.0,        // optional (kokoro only)
	"format": "wav"      // wav or mp3 for kokoro; wav for chatterbox
}
```

Responses stream progress updates (kokoro) followed by a completion message:

```json
{ "status": "ok", "file": "output/<uuid>.wav", "format": "wav" }
```

## Configuration

Environment variables (defaults shown):

- `TTS_BACKEND=kokoro` — choose `kokoro` (CPU) or `chatterbox` (GPU-preferred)
- `TTS_CHATTERBOX_DEVICE=cuda` — device passed to Chatterbox (`cuda`/`cpu`)
- `TTS_HOST=0.0.0.0`, `TTS_PORT=8000` — WebSocket bind
- `TTS_MONITORING_HOST=0.0.0.0`, `TTS_MONITORING_PORT=9093`
- `TTS_DEFAULT_VOICE=af_sarah`, `TTS_DEFAULT_LANGUAGE=en-us`, `TTS_DEFAULT_SPEED=1.0`, `TTS_DEFAULT_FORMAT=wav`
- `TTS_MODEL_PATH`, `TTS_VOICES_PATH` — Kokoro assets
- `TTS_OUTPUT_DIR=output` — where audio is written

CLI overrides mirror these flags, e.g.:

```bash
python -u main.py websocket --backend chatterbox --chatterbox-device cuda
```

## Notes

- The Docker image installs CUDA 12.1 runtime, PyTorch 2.6.0, and torchaudio 2.6.0 with `cu121` wheels.
- Kokoro continues to stream progress; Chatterbox returns a single completion message per request.
- Ensure the `output/` directory is writable when mounting volumes.
2. **Clone the Git repository, build the Docker image, and then run it**.



## Ways to Run



### Option 1: Pull the Docker Image and Run

