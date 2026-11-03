"""Compatibility import; implementation lives in app.answers.orchestration."""
import sys
from app.answers import orchestration as _implementation
sys.modules[__name__] = _implementation
