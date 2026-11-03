from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profiles.profile_builder import build_profiles


def main() -> None:
    report = build_profiles()
    report_path = ROOT / "reports" / "profile_build_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = [
        "# Profile Build Report",
        "",
        f"- Raw rows: {report['raw_rows']:,}",
        f"- Parsed unique profiles: {report['parsed_profiles']:,}",
        f"- Duplicate raw rows suppressed: {report['duplicate_raw_rows_suppressed']:,}",
        f"- Eligible profiles: {report['eligible_rows']:,}",
        f"- Excluded profiles: {report['excluded_rows']:,}",
        f"- Interest coverage: {report['interest_coverage']:.1%}",
        f"- Product-affinity coverage: {report['product_affinity_coverage']:.1%}",
        f"- Professional-subtype coverage: {report['professional_subtype_coverage']:.1%}",
        f"- Finance-subtype coverage: {report['finance_subtype_coverage']:.1%}",
        f"- Rows with no evidence: {report['rows_with_no_evidence']:,}",
        f"- Rows with conflicting locations: {report['rows_with_conflicting_locations']:,}",
        f"- Rows with unknown roles: {report['rows_with_unknown_roles']:,}",
        f"- Build time: {report['build_ms']:,} ms",
        "",
        "## Output Hashes",
        "",
        f"- JSONL: `{report['jsonl_sha256']}`",
        f"- CSV: `{report['csv_sha256']}`",
        "",
        "## Role Distribution",
        "",
    ]
    markdown.extend(f"- {name}: {count:,}" for name, count in report["role_distribution"].items())
    markdown.extend(["", "## Category Distribution", ""])
    markdown.extend(f"- {name}: {count:,}" for name, count in report["category_distribution"].items())
    markdown.extend(["", "## Exclusion Reasons", ""])
    markdown.extend(f"- {name}: {count:,}" for name, count in report["exclusion_reason_distribution"].items())
    (ROOT / "reports" / "profile_build_report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()

