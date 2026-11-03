"""Compatibility import; implementation lives in app.answers.safety."""
import sys
from app.answers import safety as _implementation
sys.modules[__name__] = _implementation
