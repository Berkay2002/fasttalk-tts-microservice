"""
Modernised WebSocket launcher for the TTS service.

Implements the same lifecycle plumbing used by the STT and LLM services while
still delegating synthesis work to the legacy Kokoro implementation.
"""

from __future__ import annotations

import asyncio
import json
import signal
import time
from pathlib import Path
from typing import Optional
from uuid import uuid4

import soundfile as sf  # type: ignore
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.server import WebSocketServerProtocol

from app.core.backends import build_backend
from app.monitoring.service_monitor import ServiceMonitor
from app.utils.config import Config
from app.utils.connection_manager import ConnectionManager
from app.utils.logger import get_logger


class WebSocketLauncher:
    """Lifecycle manager for the TTS WebSocket server."""

    def __init__(self, config: Optional[Config] = None, monitor: Optional[ServiceMonitor] = None) -> None:
        self.config = config or Config()
        self.monitor = monitor or ServiceMonitor()
        self.connection_manager = ConnectionManager(self.config.max_connections)
        self.logger = get_logger("tts.websocket")
        self.backend = build_backend(self.config)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    # ----------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Start the WebSocket server."""
        if self._loop and self._loop.is_running():
            self.logger.info("WebSocket event loop already running")
            return

        self.logger.info(
            "Starting TTS WebSocket server",
            host=self.config.host,
            port=self.config.port,
            max_connections=self.config.max_connections,
            backend=self.backend.name,
        )

        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            self.logger.info("TTS WebSocket server interrupted by user")

    def _handle_signal(self, signum, _frame) -> None:
        self.logger.info(f"Received signal {signum}, shutting down TTS WebSocket server")
        if self._loop and self._loop.is_running():
            self._loop.stop()

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        async with websockets.serve(self._handle_connection, self.config.host, self.config.port):
            self.logger.info(f"TTS WebSocket server ready on ws://{self.config.host}:{self.config.port}")
            await asyncio.Future()  # Run forever

    # ----------------------------------------------------------------- handlers
    async def _handle_connection(self, websocket: WebSocketServerProtocol) -> None:
        session_id = uuid4().hex
        remote = None
        if websocket.remote_address:
            host, port, *_ = (*websocket.remote_address, None, None)
            remote = f"{host}:{port}"

        if not self.connection_manager.add_connection(session_id, client=remote):
            self.logger.warning("Rejecting connection (max connections reached)", client=remote)
            await websocket.close(code=1013, reason="Service busy")
            self.monitor.record_error()
            return

        self.monitor.record_connection_open()
        self.logger.info("Client connected", session_id=session_id, client=remote)

        try:
            async for message in websocket:
                self.connection_manager.record_message_received(session_id)
                await self._process_message(websocket, session_id, message)
        except (ConnectionClosedOK, ConnectionClosedError):
            self.logger.info("Client disconnected", session_id=session_id, client=remote)
        except Exception as exc:  # noqa: broad-except - defensive guard
            self.logger.error(
                "Unexpected error while handling connection",
                session_id=session_id,
                client=remote,
                exc_info=exc,
            )
            self.monitor.record_error()
        finally:
            self.connection_manager.remove_connection(session_id)
            self.monitor.record_connection_closed()

    async def _process_message(self, websocket: WebSocketServerProtocol, session_id: str, message: str) -> None:
        request_id = uuid4().hex
        self.monitor.record_request()

        with self.logger.request_context(request_id):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                self.monitor.record_error()
                await self._send_json(websocket, {"status": "error", "message": "Invalid JSON payload"})
                self.connection_manager.record_message_sent(session_id)
                self.logger.warning("Rejected request due to invalid JSON", session_id=session_id)
                return

            text = payload.get("text")
            if not text:
                self.monitor.record_error()
                await self._send_json(websocket, {"status": "error", "message": "No text provided"})
                self.connection_manager.record_message_sent(session_id)
                self.logger.warning("Rejected request with missing text", session_id=session_id)
                return

            lang = payload.get("lang", self.config.default_language)
            voice = payload.get("voice") or self.config.default_voice
            speed_raw = payload.get("speed", self.config.default_speed)
            fmt = (payload.get("format") or self.config.default_format).lower()

            try:
                speed = float(speed_raw)
            except (TypeError, ValueError):
                speed = self.config.default_speed

            if fmt not in {"wav", "mp3"}:
                self.monitor.record_error()
                await self._send_json(websocket, {"status": "error", "message": f"Unsupported format '{fmt}'"})
                self.connection_manager.record_message_sent(session_id)
                self.logger.warning("Unsupported audio format", session_id=session_id, format=fmt)
                return

            if self.config.backend == "chatterbox" and fmt != "wav":
                self.monitor.record_error()
                await self._send_json(websocket, {"status": "error", "message": "Chatterbox only supports WAV"})
                self.connection_manager.record_message_sent(session_id)
                self.logger.warning("Unsupported audio format", session_id=session_id, format=fmt)
                return

            output_dir = Path(self.config.output_directory)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{uuid4()}.{fmt}"

            success = False
            audio_duration = 0.0
            characters = len(text)
            start_time = time.time()

            try:
                for update in self.backend.synthesize(
                    text=text,
                    output_file=output_file,
                    voice=voice,
                    speed=speed,
                    lang=lang,
                    fmt=fmt,
                ):
                    if "progress" in update:
                        await self._send_json(websocket, {"status": "progress", "progress": update["progress"]})
                        self.connection_manager.record_message_sent(session_id)
                    elif "done" in update:
                        await self._send_json(
                            websocket,
                            {
                                "status": "ok",
                                "file": str(update["file"]),
                                "format": update["format"],
                            },
                        )
                        self.connection_manager.record_message_sent(session_id)
                        success = True
                        try:
                            info = sf.info(str(update["file"]))
                            audio_duration = float(getattr(info, "duration", 0.0) or 0.0)
                        except Exception:  # noqa: broad-except - best effort
                            audio_duration = 0.0

                self.connection_manager.record_characters(session_id, characters)
                self.logger.info(
                    "Synthesis completed",
                    session_id=session_id,
                    characters=characters,
                    voice=voice,
                    language=lang,
                    processing_time=round(time.time() - start_time, 3),
                )
            except Exception as exc:  # noqa: broad-except - surface the error to the client
                self.monitor.record_error()
                self.connection_manager.record_error(session_id)
                await self._send_json(websocket, {"status": "error", "message": str(exc)})
                self.connection_manager.record_message_sent(session_id)
                self.logger.error(
                    "Synthesis failed",
                    session_id=session_id,
                    characters=characters,
                    voice=voice,
                    language=lang,
                    exc_info=exc,
                )
            finally:
                processing_time = time.time() - start_time
                self.monitor.record_synthesis(
                    characters=characters,
                    processing_time=processing_time,
                    audio_duration=audio_duration,
                    success=success,
                )

    # ----------------------------------------------------------------- helpers
    async def _send_json(self, websocket: WebSocketServerProtocol, payload: dict) -> None:
        await websocket.send(json.dumps(payload))
