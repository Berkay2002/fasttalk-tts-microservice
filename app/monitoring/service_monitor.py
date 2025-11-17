"""
Monitoring and health check utilities for the TTS service.

Implements the same API shape used by the STT and LLM microservices so the
platform can query consistent endpoints across services.
"""

from __future__ import annotations

import logging
import time
from threading import Lock, Thread
from typing import Any, Dict, Optional

import psutil
from flask import Flask, jsonify

logger = logging.getLogger(__name__)


class ServiceMonitor:
    """Collects runtime metrics for the TTS service."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    # ----------------------------------------------------------------- lifecycle
    def reset(self) -> None:
        with self._lock:
            self.start_time = time.time()
            self.request_count = 0
            self.synthesis_count = 0
            self.error_count = 0
            self.total_characters = 0
            self.total_processing_time = 0.0
            self.total_audio_duration = 0.0
            self.active_connections = 0
            self.peak_connections = 0

    # ---------------------------------------------------------------- metrics api
    def record_connection_open(self) -> None:
        with self._lock:
            self.active_connections += 1
            if self.active_connections > self.peak_connections:
                self.peak_connections = self.active_connections

    def record_connection_closed(self) -> None:
        with self._lock:
            self.active_connections = max(0, self.active_connections - 1)

    def record_request(self) -> None:
        with self._lock:
            self.request_count += 1

    def record_error(self) -> None:
        with self._lock:
            self.error_count += 1

    def record_synthesis(
        self,
        *,
        characters: int,
        processing_time: float,
        audio_duration: float = 0.0,
        success: bool = True,
    ) -> None:
        with self._lock:
            self.synthesis_count += 1
            self.total_characters += max(characters, 0)
            self.total_processing_time += max(processing_time, 0.0)
            self.total_audio_duration += max(audio_duration, 0.0)

    # ---------------------------------------------------------------- getters
    def uptime(self) -> float:
        with self._lock:
            return time.time() - self.start_time

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            avg_processing_time = (
                self.total_processing_time / self.synthesis_count if self.synthesis_count else 0.0
            )
            avg_characters = self.total_characters / self.synthesis_count if self.synthesis_count else 0.0
            avg_audio_duration = (
                self.total_audio_duration / self.synthesis_count if self.synthesis_count else 0.0
            )

            return {
                "uptime_seconds": self.uptime(),
                "requests_total": self.request_count,
                "syntheses_total": self.synthesis_count,
                "errors_total": self.error_count,
                "total_characters": self.total_characters,
                "total_audio_duration_seconds": self.total_audio_duration,
                "avg_processing_time_seconds": avg_processing_time,
                "avg_characters": avg_characters,
                "avg_audio_duration_seconds": avg_audio_duration,
                "active_connections": self.active_connections,
                "peak_connections": self.peak_connections,
            }


class MonitoringServer:
    """Simple Flask server that exposes health and metrics endpoints."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9093, monitor: Optional[ServiceMonitor] = None) -> None:
        self.host = host
        self.port = port
        self.monitor = monitor or ServiceMonitor()
        self._thread: Optional[Thread] = None
        self.app = Flask("tts-monitoring")
        self._register_routes()

    # ----------------------------------------------------------------- routing
    def _register_routes(self) -> None:
        @self.app.route("/health", methods=["GET"])
        def health() -> Any:
            """Combined health check with system metrics."""
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            status = "healthy"
            warnings = []

            if cpu_percent > 90:
                warnings.append("High CPU usage")
            if memory.percent > 90:
                warnings.append("High memory usage")
            if self.monitor.error_count > 0:
                warnings.append("Recent synthesis errors detected")

            if warnings:
                status = "degraded"

            return jsonify(
                {
                    "status": status,
                    "uptime_seconds": self.monitor.uptime(),
                    "metrics": self.monitor.get_metrics(),
                    "system": {
                        "cpu_percent": cpu_percent,
                        "memory_percent": memory.percent,
                        "memory_available_gb": memory.available / (1024**3),
                    },
                    "warnings": warnings,
                }
            )

        @self.app.route("/health/live", methods=["GET"])
        def live() -> Any:
            """Liveness probe."""
            return jsonify({"status": "live"})

        @self.app.route("/health/ready", methods=["GET"])
        def ready() -> Any:
            """Readiness probe."""
            return jsonify({"status": "ready" if self.monitor.active_connections >= 0 else "starting"})

        @self.app.route("/metrics", methods=["GET"])
        def metrics() -> Any:
            """Expose collected runtime metrics."""
            return jsonify(self.monitor.get_metrics())

        @self.app.route("/info", methods=["GET"])
        def info() -> Any:
            """Basic service descriptor."""
            return jsonify(
                {
                    "service": "tts-service",
                    "version": "1.0.0",
                    "host": self.host,
                    "port": self.port,
                    "uptime_seconds": self.monitor.uptime(),
                }
            )

    # ----------------------------------------------------------------- control
    def start(self) -> None:
        """Start the monitoring server in a background thread."""
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            logger.info("Starting TTS monitoring server on %s:%s", self.host, self.port)
            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

        self._thread = Thread(target=_run, daemon=True)
        self._thread.start()

    def run(self, debug: bool = False) -> None:
        """Run the monitoring server in the current thread."""
        logger.info("Running TTS monitoring server on %s:%s", self.host, self.port)
        self.app.run(host=self.host, port=self.port, debug=debug, use_reloader=False)
