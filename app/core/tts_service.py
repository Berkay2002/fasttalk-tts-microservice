"""
Compatibility layer that re-exports the legacy Kokoro implementation.

Keeping this module in `app.core` ensures existing imports continue working
after relocating the original code under `app.legacy`.
"""

from app.legacy.tts_service import *  # noqa: F401,F403
