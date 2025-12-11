"""Backend selection for TTS engines.

Provides a thin abstraction so the WebSocket server can drive either the
existing Kokoro (CPU) pipeline or the new Chatterbox (GPU-preferred) pipeline
without changing request handling code.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Iterable

import torchaudio  # type: ignore

from app.utils.logger import get_logger


class BaseBackend:
    """Minimal interface for a synthesis backend."""

    name: str = "base"

    def synthesize(
        self,
        *,
        text: str,
        lang: str,
        voice: str,
        speed: float,
        fmt: str,
        output_file: Path,
    ) -> Iterable[Dict]:  # pragma: no cover - small glue wrapper
        raise NotImplementedError


class KokoroBackend(BaseBackend):
    name = "kokoro"

    def __init__(self, *, model_path: str, voices_path: str) -> None:
        from app.legacy import tts_service as kokoro_legacy

        self._kokoro = kokoro_legacy
        self.model_path = model_path
        self.voices_path = voices_path

    def synthesize(
        self,
        *,
        text: str,
        lang: str,
        voice: str,
        speed: float,
        fmt: str,
        output_file: Path,
    ):
        yield from self._kokoro.convert_text_to_audio_text(
            text=text,
            output_file=str(output_file),
            voice=voice,
            speed=speed,
            lang=lang,
            format=fmt,
            debug=False,
            model_path=self.model_path,
            voices_path=self.voices_path,
        )


class ChatterboxBackend(BaseBackend):
    name = "chatterbox"

    def __init__(self, *, device: str = "cuda") -> None:
        self.device = device
        self._logger = get_logger("tts.backend.chatterbox")
        self._ensure_path()
        self._model = self._load_model()

    def _ensure_path(self) -> None:
        src_path = Path(__file__).resolve().parents[2] / "chatterbox" / "src"
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

    def _load_model(self):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        import torch

        model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
        self._logger.info(
            "Loaded Chatterbox model",
            torch_version=torch.__version__,
            cuda_available=torch.cuda.is_available(),
            device=self.device,
        )
        return model

    def synthesize(
        self,
        *,
        text: str,
        lang: str,
        voice: str,
        speed: float,
        fmt: str,
        output_file: Path,
    ):
        if fmt != "wav":
            raise ValueError("Chatterbox backend only supports WAV output today")

        wav = self._model.generate(text, language_id=lang)
        torchaudio.save(str(output_file), wav, self._model.sr)
        yield {"done": True, "file": output_file, "format": fmt}


def build_backend(config) -> BaseBackend:
    """Factory that returns the configured backend instance."""
    if getattr(config, "backend", "kokoro") == "chatterbox":
        return ChatterboxBackend(device=getattr(config, "chatterbox_device", "cuda"))
    return KokoroBackend(model_path=config.model_path, voices_path=config.voices_path)
