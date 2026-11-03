"""Compatibility import; implementation lives in app.knowledge.thresholds."""
import sys
from app.knowledge import thresholds as _implementation
sys.modules[__name__] = _implementation
