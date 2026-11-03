"""Compatibility import; implementation lives in app.voice.providers.soniox."""
import sys
from app.voice.providers import soniox as _implementation
sys.modules[__name__] = _implementation
