"""
Compatibility layer exposing the legacy Kokoro WebSocket handlers under the
standardized module name used by other microservices.
"""

from app.core.tts_service import main_ws, tts_handler  # noqa: F401
