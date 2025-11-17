"""
TTS service package initializer.

Re-exports the legacy Kokoro TTS module to maintain backward compatibility
after reorganizing the project structure.
"""

from app.core.tts_service import *  # noqa: F401,F403
