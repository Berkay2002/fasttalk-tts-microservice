"""
RealtimeTTS WebSocket handler for FastTalk TTS microservice.

Provides streaming text-to-speech synthesis with real-time audio chunk delivery
via WebSocket, supporting multiple engines (Kokoro, Coqui, Orpheus).
"""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import soundfile as sf
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.server import WebSocketServerProtocol

from app.core.audio_processor import AudioProcessor
from app.monitoring.service_monitor import ServiceMonitor
from app.utils.config import Config
from app.utils.logger import get_logger

logger = get_logger("tts.realtime_handler")

class RealtimeTTSHandler:
    """
    WebSocket handler for real-time TTS synthesis using RealtimeTTS.

    Supports streaming audio synthesis with real-time chunk delivery,
    multiple TTS engines, and proper error handling.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        monitor: Optional[ServiceMonitor] = None
    ) -> None:
        self.config = config or Config()
        self.monitor = monitor or ServiceMonitor()
        self.audio_processor: Optional[AudioProcessor] = None
        self._initialize_processor()

    def _initialize_processor(self) -> None:
        """Initialize the AudioProcessor with configured engine."""
        try:
            engine = self.config.tts_engine.lower()
            kokoro_voice = getattr(self.config, 'kokoro_voice', 'af_bella')
            orpheus_model = getattr(self.config, 'orpheus_model', 'orpheus-3b-0.1-ft-Q8_0-GGUF/orpheus-3b-0.1-ft-q8_0.gguf')

            self.audio_processor = AudioProcessor(
                engine=engine,
                kokoro_voice=kokoro_voice,
                orpheus_model=orpheus_model
            )

            logger.info(
                "RealtimeTTS AudioProcessor initialized",
                engine=engine,
                kokoro_voice=kokoro_voice if engine == "kokoro" else None,
                orpheus_model=orpheus_model if engine == "orpheus" else None,
                ttfa_ms=self.audio_processor.tts_inference_time
            )
        except Exception as exc:
            logger.error(
                "Failed to initialize RealtimeTTS AudioProcessor",
                exc_info=exc
            )
            self.monitor.record_error()
            raise

    async def handle_websocket(self, websocket: WebSocketServerProtocol) -> None:
        """
        Handle WebSocket connection for real-time TTS synthesis.

        Expected protocol:
        Client -> Server:
        {
            "type": "synthesize",
            "text": "Hello world",
            "engine": "kokoro",  // optional, defaults to config
            "voice": "af_bella", // optional, defaults to config
            "speed": 1.0,        // optional
            "stream": true       // optional, whether to stream chunks
        }

        Server -> Client (streaming):
        {"type": "chunk", "data": "base64_encoded_audio_chunk", "index": 0}
        {"type": "complete", "duration": 2.5, "chunks": 5}
        {"type": "error", "message": "..."}
        """
        session_id = uuid.uuid4().hex
        remote = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}" if websocket.remote_address else "unknown"

        logger.info("RealtimeTTS WebSocket connection established", session_id=session_id, client=remote)

        try:
            async for message in websocket:
                await self._process_message(websocket, session_id, message)
        except (ConnectionClosedOK, ConnectionClosedError):
            logger.info("RealtimeTTS WebSocket connection closed", session_id=session_id, client=remote)
        except Exception as exc:
            logger.error(
                "Unexpected error in RealtimeTTS WebSocket handler",
                session_id=session_id,
                client=remote,
                exc_info=exc
            )
            self.monitor.record_error()
        finally:
            logger.info("RealtimeTTS WebSocket connection cleanup", session_id=session_id)

    async def _process_message(
        self,
        websocket: WebSocketServerProtocol,
        session_id: str,
        message: str
    ) -> None:
        """Process incoming WebSocket message."""
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            await self._send_error(websocket, "Invalid JSON payload")
            self.monitor.record_error()
            return

        message_type = payload.get("type")

        if message_type != "synthesize":
            await self._send_error(websocket, f"Unsupported message type: {message_type}")
            self.monitor.record_error()
            return

        text = payload.get("text")
        if not text:
            await self._send_error(websocket, "No text provided")
            self.monitor.record_error()
            return

        # Extract optional parameters
        engine = payload.get("engine")
        voice = payload.get("voice")
        speed = float(payload.get("speed", 1.0))
        stream_chunks = payload.get("stream", True)

        # Reinitialize processor if engine or voice changed
        if engine and engine != self.audio_processor.engine_name:
            try:
                kokoro_voice = voice if engine == "kokoro" else getattr(self.config, 'kokoro_voice', 'af_bella')
                orpheus_model = getattr(self.config, 'orpheus_model', 'orpheus-3b-0.1-ft-Q8_0-GGUF/orpheus-3b-0.1-ft-q8_0.gguf')

                self.audio_processor = AudioProcessor(
                    engine=engine,
                    kokoro_voice=kokoro_voice,
                    orpheus_model=orpheus_model
                )
                logger.info("RealtimeTTS engine switched", engine=engine, session_id=session_id)
            except Exception as exc:
                await self._send_error(websocket, f"Failed to initialize engine {engine}: {str(exc)}")
                self.monitor.record_error()
                return

        start_time = time.time()
        characters = len(text)

        try:
            if stream_chunks:
                await self._stream_synthesis(websocket, session_id, text, speed)
            else:
                await self._batch_synthesis(websocket, session_id, text, speed)

            processing_time = time.time() - start_time
            self.monitor.record_synthesis(
                characters=characters,
                processing_time=processing_time,
                audio_duration=0.0,  # Could be calculated if needed
                success=True
            )

            logger.info(
                "TTS synthesis completed",
                session_id=session_id,
                characters=characters,
                processing_time=round(processing_time, 3),
                engine=self.audio_processor.engine_name
            )

        except Exception as exc:
            processing_time = time.time() - start_time
            self.monitor.record_synthesis(
                characters=characters,
                processing_time=processing_time,
                audio_duration=0.0,
                success=False
            )
            self.monitor.record_error()

            await self._send_error(websocket, f"Synthesis failed: {str(exc)}")
            logger.error(
                "TTS synthesis failed",
                session_id=session_id,
                characters=characters,
                engine=self.audio_processor.engine_name,
                exc_info=exc
            )

    async def _stream_synthesis(
        self,
        websocket: WebSocketServerProtocol,
        session_id: str,
        text: str,
        speed: float
    ) -> None:
        """Stream audio chunks in real-time as they are generated."""
        if not self.audio_processor:
            raise RuntimeError("AudioProcessor not initialized")

        # Create a queue for audio chunks
        audio_queue = asyncio.Queue()
        stop_event = asyncio.Event()

        # Modify engine speed if specified
        original_speed = None
        if hasattr(self.audio_processor.engine, 'speed') and speed != 1.0:
            original_speed = self.audio_processor.engine.speed
            self.audio_processor.engine.speed = speed

        # Start synthesis in background
        synthesis_task = asyncio.create_task(
            self._run_synthesis_background(audio_queue, stop_event, text, session_id)
        )

        chunk_index = 0
        try:
            # Stream audio chunks as they become available
            while not synthesis_task.done() or not audio_queue.empty():
                try:
                    # Get chunk with timeout to allow checking synthesis task
                    chunk_data = await asyncio.wait_for(audio_queue.get(), timeout=0.1)

                    if chunk_data is None:  # End signal
                        break

                    # Send chunk to client
                    chunk_b64 = chunk_data  # Assuming chunks are already bytes/base64 encoded
                    await self._send_chunk(websocket, chunk_index, chunk_b64)
                    chunk_index += 1

                except asyncio.TimeoutError:
                    # Check if synthesis task is done
                    if synthesis_task.done():
                        break
                    continue

            # Wait for synthesis to complete
            await synthesis_task

            # Send completion message
            await self._send_complete(websocket, chunk_index)

        except Exception as exc:
            stop_event.set()
            synthesis_task.cancel()
            raise exc
        finally:
            # Restore original speed if modified
            if original_speed is not None:
                self.audio_processor.engine.speed = original_speed

    async def _batch_synthesis(
        self,
        websocket: WebSocketServerProtocol,
        session_id: str,
        text: str,
        speed: float
    ) -> None:
        """Generate complete audio file and send as single response."""
        if not self.audio_processor:
            raise RuntimeError("AudioProcessor not initialized")

        # Create temporary output file
        output_dir = Path(self.config.output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{uuid.uuid4()}.wav"

        # Modify engine speed if specified
        original_speed = None
        if hasattr(self.audio_processor.engine, 'speed') and speed != 1.0:
            original_speed = self.audio_processor.engine.speed
            self.audio_processor.engine.speed = speed

        try:
            # Use AudioProcessor to generate complete audio
            from queue import Queue
            from threading import Event

            audio_queue = Queue()
            stop_event = Event()

            success = self.audio_processor.synthesize(
                text=text,
                audio_chunks=audio_queue,
                stop_event=stop_event,
                generation_string=f"batch_{session_id}"
            )

            if not success:
                raise RuntimeError("Audio synthesis was interrupted")

            # Collect all chunks and save to file
            all_chunks = []
            while not audio_queue.empty():
                chunk = audio_queue.get_nowait()
                all_chunks.append(chunk)

            if not all_chunks:
                raise RuntimeError("No audio chunks generated")

            # Save to file
            import numpy as np
            audio_data = np.concatenate([np.frombuffer(chunk, dtype=np.int16) for chunk in all_chunks])
            sf.write(str(output_file), audio_data, 24000)

            # Send file info to client
            await self._send_file_complete(websocket, str(output_file))

        finally:
            # Restore original speed if modified
            if original_speed is not None:
                self.audio_processor.engine.speed = original_speed

    async def _run_synthesis_background(
        self,
        audio_queue: asyncio.Queue,
        stop_event: asyncio.Event,
        text: str,
        session_id: str
    ) -> None:
        """Run audio synthesis in background thread and put chunks in queue."""
        def synthesis_worker():
            try:
                from queue import Queue
                from threading import Event

                # Convert asyncio queue to thread queue for AudioProcessor
                thread_queue = Queue()
                thread_stop = Event()

                # Set up stop event propagation
                def propagate_stop():
                    if stop_event.is_set():
                        thread_stop.set()
                        return True
                    return False

                # Run synthesis
                success = self.audio_processor.synthesize(
                    text=text,
                    audio_chunks=thread_queue,
                    stop_event=thread_stop,
                    generation_string=f"stream_{session_id}"
                )

                # Transfer chunks to asyncio queue
                while not thread_queue.empty() and not stop_event.is_set():
                    chunk = thread_queue.get_nowait()
                    asyncio.run_coroutine_threadsafe(
                        audio_queue.put(chunk),
                        asyncio.get_running_loop()
                    )

                # Signal completion
                asyncio.run_coroutine_threadsafe(
                    audio_queue.put(None),
                    asyncio.get_running_loop()
                )

            except Exception as exc:
                logger.error(
                    "Background synthesis failed",
                    session_id=session_id,
                    exc_info=exc
                )
                asyncio.run_coroutine_threadsafe(
                    audio_queue.put(None),
                    asyncio.get_running_loop()
                )

        # Run in thread pool to avoid blocking event loop
        await asyncio.get_running_loop().run_in_executor(None, synthesis_worker)

    async def _send_chunk(self, websocket: WebSocketServerProtocol, index: int, data: bytes) -> None:
        """Send audio chunk to client."""
        import base64
        chunk_b64 = base64.b64encode(data).decode('utf-8')
        message = {
            "type": "chunk",
            "index": index,
            "data": chunk_b64
        }
        await websocket.send(json.dumps(message))

    async def _send_complete(self, websocket: WebSocketServerProtocol, chunks: int) -> None:
        """Send completion message to client."""
        message = {
            "type": "complete",
            "chunks": chunks
        }
        await websocket.send(json.dumps(message))

    async def _send_file_complete(self, websocket: WebSocketServerProtocol, file_path: str) -> None:
        """Send file completion message to client."""
        message = {
            "type": "file_complete",
            "file": file_path
        }
        await websocket.send(json.dumps(message))

    async def _send_error(self, websocket: WebSocketServerProtocol, error_message: str) -> None:
        """Send error message to client."""
        message = {
            "type": "error",
            "message": error_message
        }
        try:
            await websocket.send(json.dumps(message))
        except (ConnectionClosedError, ConnectionClosedOK):
            pass  # Client already disconnected