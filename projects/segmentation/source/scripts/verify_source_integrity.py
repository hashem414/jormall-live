from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
BASELINE_PATH = REPORTS / "baseline_file_inventory.csv"
OUTPUT_PATH = REPORTS / "source_unchanged_verification.csv"
SUMMARY_PATH = REPORTS / "source_integrity_summary.json"
SOURCE_ROOTS_MANIFEST = Path(os.getenv("SOURCE_ROOTS_MANIFEST", str(ROOT / "config_data" / "source_roots.local.json")))
VOLATILE_TOOL_METADATA_PREFIXES = (".git\\refs\\codex\\turn-diffs\\",)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    source_payload = json.loads(SOURCE_ROOTS_MANIFEST.read_text(encoding="utf-8"))
    source_roots = {name: Path(value) for name, value in source_payload["source_roots"].items()}
    with BASELINE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        baseline_rows = list(csv.DictReader(handle))
    baseline = {
        (row["source"], row["relative_path"].replace("/", "\\")): row
        for row in baseline_rows
    }
    current: dict[tuple[str, str], Path] = {}
    for source, source_root in source_roots.items():
        for path in source_root.rglob("*"):
            if path.is_file():
                current[(source, str(path.relative_to(source_root)).replace("/", "\\"))] = path

    rows: list[dict[str, object]] = []
    for key in sorted(set(baseline) | set(current)):
        source, relative_path = key
        expected = baseline.get(key)
        path = current.get(key)
        current_hash = digest(path) if path else ""
        if expected is None:
            status = "EXTRA_TOOL_METADATA" if relative_path.startswith(VOLATILE_TOOL_METADATA_PREFIXES) else "EXTRA"
        elif path is None:
            status = "MISSING"
        elif current_hash == expected["sha256"]:
            status = "UNCHANGED"
        else:
            status = "CHANGED"
        rows.append({
            "source": source,
            "relative_path": relative_path,
            "baseline_sha256": expected["sha256"] if expected else "",
            "current_sha256": current_hash,
            "status": status,
        })

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(str(row["status"]) for row in rows)
    summary = {
        "baseline_files": len(baseline),
        "current_files": len(current),
        "status_counts": dict(sorted(counts.items())),
        "excluded_tool_metadata_files": counts["EXTRA_TOOL_METADATA"],
        "source_projects_unchanged": not any(counts[state] for state in ("CHANGED", "MISSING", "EXTRA")),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["source_projects_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
