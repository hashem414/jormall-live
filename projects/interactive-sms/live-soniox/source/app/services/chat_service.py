"""Compatibility import; implementation lives in app.answers.policy."""
import sys
from app.answers import policy as _implementation
sys.modules[__name__] = _implementation
