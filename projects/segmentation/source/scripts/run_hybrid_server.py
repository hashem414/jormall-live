from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app
from config import HOST, PORT


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
