try:
    from importlib.metadata import version
except ImportError:
    from importlib_metadata import version  # For Python <3.8

# __version__ = version("chatterbox-tts")
# from importlib.metadata import version
# __version__ = version("chatterbox-tts")

__version__ = "0.0.0"


from .tts import ChatterboxTTS
from .vc import ChatterboxVC
from .mtl_tts import ChatterboxMultilingualTTS, SUPPORTED_LANGUAGES
