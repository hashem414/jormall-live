"""Compatibility import; implementation lives in app.conversations.store."""
import sys
from app.conversations import store as _implementation
sys.modules[__name__] = _implementation
