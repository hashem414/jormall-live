"""Compatibility import; implementation lives in app.conversations.memory."""
import sys
from app.conversations import memory as _implementation
sys.modules[__name__] = _implementation
