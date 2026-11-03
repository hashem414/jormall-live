"""Compatibility import; implementation lives in app.knowledge.embeddings."""
import sys
from app.knowledge import embeddings as _implementation
sys.modules[__name__] = _implementation
