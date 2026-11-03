from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "file_change_manifest.csv"


def category(relative: Path) -> str:
    top = relative.parts[0] if len(relative.parts) > 1 else ""
    return {
        "backups": "backup",
        "data": "data",
        "reports": "report",
        "checkpoints": "checkpoint",
        "logs": "log",
        "tests": "test",
        "scripts": "script",
        "static": "frontend",
        "templates": "frontend",
    }.get(top, "source" if relative.suffix in {".py", ".ps1"} else "project_file")


def main() -> None:
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path == OUTPUT or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(ROOT)
        rows.append({
            "relative_path": str(relative),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "category": category(relative),
        })
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("relative_path", "size_bytes", "sha256", "category"))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Manifested {len(rows)} files (excluding the manifest itself and generated Python bytecode).")


if __name__ == "__main__":
    main()
