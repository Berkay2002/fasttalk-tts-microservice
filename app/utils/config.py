"""
Configuration management for the TTS service.

Mirrors the structure used by the STT and LLM services so orchestration
can rely on a consistent contract across microservices.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _bool_env(var_name: str, default: bool) -> bool:
    """Parse boolean environment variables."""
    value = os.getenv(var_name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    """
    Configuration settings for the TTS microservice.

    The defaults align with the conventions described in PORT_CONFIGURATION.md
    and are compatible with the backend-orchestration docker-compose setup.
    """

    # Server configuration -------------------------------------------------
    host: str = field(default_factory=lambda: os.getenv("TTS_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("TTS_PORT", "8000")))
    monitoring_host: str = field(default_factory=lambda: os.getenv("TTS_MONITORING_HOST", "0.0.0.0"))
    monitoring_port: int = field(default_factory=lambda: int(os.getenv("TTS_MONITORING_PORT", "9093")))
    max_connections: int = field(default_factory=lambda: int(os.getenv("TTS_MAX_CONNECTIONS", "50")))
    log_level: str = field(default_factory=lambda: os.getenv("TTS_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))

    # Synthesis defaults ---------------------------------------------------
    default_voice: str = field(default_factory=lambda: os.getenv("TTS_DEFAULT_VOICE", "af_sarah"))
    default_language: str = field(default_factory=lambda: os.getenv("TTS_DEFAULT_LANGUAGE", "en-us"))
    default_speed: float = field(default_factory=lambda: float(os.getenv("TTS_DEFAULT_SPEED", "1.0")))
    default_format: str = field(default_factory=lambda: os.getenv("TTS_DEFAULT_FORMAT", "wav"))
    allow_streaming: bool = field(default_factory=lambda: _bool_env("TTS_ALLOW_STREAMING", True))

    # Backend selection ----------------------------------------------------
    backend: str = field(default_factory=lambda: os.getenv("TTS_BACKEND", "kokoro"))
    chatterbox_device: str = field(default_factory=lambda: os.getenv("TTS_CHATTERBOX_DEVICE", "cuda"))

    # Model asset configuration -------------------------------------------
    model_path: str = field(default_factory=lambda: os.getenv("TTS_MODEL_PATH", "kokoro-v1.0.onnx"))
    voices_path: str = field(default_factory=lambda: os.getenv("TTS_VOICES_PATH", "voices-v1.0.bin"))

    # Storage --------------------------------------------------------------
    output_directory: str = field(default_factory=lambda: os.getenv("TTS_OUTPUT_DIR", "output"))
    log_directory: str = field(default_factory=lambda: os.getenv("TTS_LOG_DIR", "/app/logs"))

    def __post_init__(self) -> None:
        """Validate configuration and prepare runtime directories."""
        self._validate()
        self._ensure_directories()
        self._log_summary()

    # ------------------------------------------------------------------ utils
    def _validate(self) -> None:
        """Validate numeric ranges and basic invariants."""
        if not 1024 <= self.port <= 65535:
            raise ValueError(f"TTS_PORT must be between 1024 and 65535. Got {self.port}.")
        if not 1024 <= self.monitoring_port <= 65535:
            raise ValueError(
                f"TTS_MONITORING_PORT must be between 1024 and 65535. Got {self.monitoring_port}."
            )
        if self.max_connections < 1:
            raise ValueError("TTS_MAX_CONNECTIONS must be at least 1.")
        if self.default_format not in {"wav", "mp3"}:
            raise ValueError("TTS_DEFAULT_FORMAT must be either 'wav' or 'mp3'.")
        if self.backend not in {"kokoro", "chatterbox"}:
            raise ValueError("TTS_BACKEND must be either 'kokoro' or 'chatterbox'.")

    def _ensure_directories(self) -> None:
        """Create directories required at runtime if they are missing."""
        try:
            Path(self.output_directory).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(f"Unable to ensure output directory {self.output_directory}: {exc}")

        try:
            Path(self.log_directory).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(f"Unable to ensure log directory {self.log_directory}: {exc}")

    def _log_summary(self) -> None:
        """Emit a concise configuration summary for diagnostics."""
        logger.info(
            "TTS configuration: host=%s port=%s monitoring_port=%s max_connections=%s",
            self.host,
            self.port,
            self.monitoring_port,
            self.max_connections,
        )
        logger.info(
            "TTS defaults: voice=%s language=%s speed=%s format=%s",
            self.default_voice,
            self.default_language,
            self.default_speed,
            self.default_format,
        )
        logger.info(
            "TTS assets: model=%s voices=%s output_dir=%s",
            self.model_path,
            self.voices_path,
            self.output_directory,
        )
        logger.info("TTS backend: %s (device=%s)", self.backend, self.chatterbox_device)

    # ----------------------------------------------------------------- helpers
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration details as a dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "monitoring_host": self.monitoring_host,
            "monitoring_port": self.monitoring_port,
            "max_connections": self.max_connections,
            "log_level": self.log_level,
            "default_voice": self.default_voice,
            "default_language": self.default_language,
            "default_speed": self.default_speed,
            "default_format": self.default_format,
            "backend": self.backend,
            "chatterbox_device": self.chatterbox_device,
            "model_path": self.model_path,
            "voices_path": self.voices_path,
            "output_directory": self.output_directory,
            "log_directory": self.log_directory,
            "allow_streaming": self.allow_streaming,
        }


def load_config() -> Config:
    """Convenience helper mirroring other microservices."""
    return Config()
