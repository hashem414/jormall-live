"""Compatibility import; implementation lives in app.knowledge.retrieval."""
import sys
from app.knowledge import retrieval as _implementation
sys.modules[__name__] = _implementation
