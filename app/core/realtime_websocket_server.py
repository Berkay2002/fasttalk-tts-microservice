"""
RealtimeTTS WebSocket server for FastTalk TTS microservice.

Provides a modern WebSocket server using RealtimeTTS for low-latency
text-to-speech synthesis with streaming audio delivery.
"""

import asyncio
import signal
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

from app.core.realtime_tts_handler import RealtimeTTSHandler
from app.monitoring.service_monitor import ServiceMonitor
from app.utils.config import Config
from app.utils.connection_manager import ConnectionManager
from app.utils.logger import get_logger

logger = get_logger("tts.realtime_server")

class RealtimeWebSocketServer:
    """
    WebSocket server for RealtimeTTS-based text-to-speech synthesis.

    Provides low-latency streaming TTS with support for multiple engines
    (Kokoro, Coqui, Orpheus) and real-time audio chunk delivery.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        monitor: Optional[ServiceMonitor] = None
    ) -> None:
        self.config = config or Config()
        self.monitor = monitor or ServiceMonitor()
        self.connection_manager = ConnectionManager(self.config.max_connections)
        self.tts_handler = RealtimeTTSHandler(config, monitor)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def start(self) -> None:
        """Start the RealtimeTTS WebSocket server."""
        if self._loop and self._loop.is_running():
            logger.info("RealtimeTTS WebSocket event loop already running")
            return

        logger.info(
            "Starting RealtimeTTS WebSocket server",
            host=self.config.host,
            port=self.config.port,
            max_connections=self.config.max_connections,
            tts_engine=self.config.tts_engine
        )

        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            logger.info("RealtimeTTS WebSocket server interrupted by user")

    def _handle_signal(self, signum, _frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down RealtimeTTS WebSocket server")
        if self._loop and self._loop.is_running():
            self._loop.stop()

    async def _run(self) -> None:
        """Run the WebSocket server."""
        self._loop = asyncio.get_running_loop()

        async def handle_connection(websocket: WebSocketServerProtocol):
            """Handle incoming WebSocket connection."""
            remote = None
            if websocket.remote_address:
                host, port, *_ = (*websocket.remote_address, None, None)
                remote = f"{host}:{port}"

            session_id = self.connection_manager.generate_session_id()

            if not self.connection_manager.add_connection(session_id, client=remote):
                logger.warning("Rejecting connection (max connections reached)", client=remote)
                await websocket.close(code=1013, reason="Service busy")
                self.monitor.record_error()
                return

            self.monitor.record_connection_open()
            logger.info("RealtimeTTS client connected", session_id=session_id, client=remote)

            try:
                await self.tts_handler.handle_websocket(websocket)
            except Exception as exc:
                logger.error(
                    "Error in RealtimeTTS connection handler",
                    session_id=session_id,
                    client=remote,
                    exc_info=exc
                )
                self.monitor.record_error()
            finally:
                self.connection_manager.remove_connection(session_id)
                self.monitor.record_connection_closed()
                logger.info("RealtimeTTS client disconnected", session_id=session_id, client=remote)

        # Start WebSocket server
        async with websockets.serve(
            handle_connection,
            self.config.host,
            self.config.port,
            max_size=10**7,  # 10MB max message size
            ping_interval=20,
            ping_timeout=10
        ):
            logger.info(
                f"RealtimeTTS WebSocket server ready on ws://{self.config.host}:{self.config.port}"
            )
            logger.info(
                f"Using TTS engine: {self.config.tts_engine} "
                f"({'GPU accelerated' if self.config.tts_engine == 'kokoro' else 'CPU'})"
            )
            await asyncio.Future()  # Run forever