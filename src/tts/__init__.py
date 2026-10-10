"""Optional text-to-speech, shipped as a light weight model the user installs."""
from .provider import (DEFAULT_LANG, DEFAULT_VOICE, KokoroProvider, TtsUnavailable,
                       available, build_provider, metadata, model_dir, model_paths)

__all__ = ("DEFAULT_LANG", "DEFAULT_VOICE", "KokoroProvider", "TtsUnavailable",
           "available", "build_provider", "metadata", "model_dir", "model_paths")
