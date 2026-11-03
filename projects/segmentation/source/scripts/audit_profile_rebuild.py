from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import EXCLUSION_RULES_PATH, PROFILES_JSONL_PATH, RAW_CATALOGUE_PATH
from profiles.exclusions import exclusion_matches
from profiles.profile_builder import build_profile, load_profiles
from profiles.raw_parser import read_raw_catalogue


REPORT_DIR = ROOT / "reports" / "smart_rebuild"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    baseline_metrics_path = REPORT_DIR / "baseline_metrics.json"
    expected_eligible = json.loads(baseline_metrics_path.read_text(encoding="utf-8"))["profiles"]["eligible"]
    baseline_candidates = list((ROOT / "backups").rglob("list_profiles.jsonl"))
    before_profiles = next(
        profiles
        for path in baseline_candidates
        for profiles in [load_profiles(path)]
        if sum(profile.eligible for profile in profiles) == expected_eligible
    )
    before = {profile.list_id: profile for profile in before_profiles}
    raw_rows = list(read_raw_catalogue(RAW_CATALOGUE_PATH))
    after = {str(row["list_id"]): build_profile(row) for row in raw_rows}

    metrics = {
        "before": _coverage(before.values()),
        "after": _coverage(after.values()),
    }
    (REPORT_DIR / "profile_coverage_before_after.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    geography_path = REPORT_DIR / "geography_before_after.csv"
    with geography_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["list_id", "list_name", "before_cities", "before_areas", "before_coverage", "after_governorates", "after_cities", "after_areas", "after_coverage"])
        writer.writeheader()
        for list_id, profile in sorted(after.items()):
            old = before.get(list_id)
            if old and (old.cities, old.areas, old.coverage_type) == (profile.cities, profile.areas, profile.coverage_type):
                continue
            writer.writerow({
                "list_id": list_id,
                "list_name": profile.list_name,
                "before_cities": json.dumps(old.cities if old else []),
                "before_areas": json.dumps(old.areas if old else []),
                "before_coverage": old.coverage_type if old else "missing",
                "after_governorates": json.dumps(profile.governorates),
                "after_cities": json.dumps(profile.cities),
                "after_areas": json.dumps(profile.areas),
                "after_coverage": profile.coverage_type,
            })

    rule_payload = json.loads(EXCLUSION_RULES_PATH.read_text(encoding="utf-8"))
    raw_by_id = {str(row["list_id"]): row for row in raw_rows}
    matches_by_rule = {str(rule["rule_id"]): [] for rule in rule_payload["rules"]}
    for list_id, row in raw_by_id.items():
        for match in exclusion_matches(row):
            matches_by_rule[str(match["rule_id"])].append((after[list_id], match))
    exclusion_path = REPORT_DIR / "exclusion_rule_audit.csv"
    with exclusion_path.open("w", encoding="utf-8-sig", newline="") as handle:
        columns = ["rule_id", "purpose", "exclude", "profiles_matched", "newest_date", "category_distribution", "role_distribution", "sample_rows"]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for rule in rule_payload["rules"]:
            matched = matches_by_rule[str(rule["rule_id"])]
            profiles = [profile for profile, _match in matched]
            writer.writerow({
                "rule_id": rule["rule_id"],
                "purpose": rule["purpose"],
                "exclude": rule.get("exclude", True),
                "profiles_matched": len(profiles),
                "newest_date": max((profile.list_date or "" for profile in profiles), default=""),
                "category_distribution": json.dumps(Counter(profile.category_group for profile in profiles).most_common(), ensure_ascii=False),
                "role_distribution": json.dumps(Counter(profile.audience_role for profile in profiles).most_common(), ensure_ascii=False),
                "sample_rows": json.dumps([profile.list_name for profile in profiles[:5]], ensure_ascii=False),
            })
    print(json.dumps(metrics, indent=2))


def _coverage(profiles: object) -> dict[str, object]:
    values = list(profiles)
    total = len(values)
    return {
        "total": total,
        "eligible": sum(profile.eligible for profile in values),
        "unknown_roles": sum(profile.audience_role == "unknown" for profile in values),
        "unknown_role_percent": round(100 * sum(profile.audience_role == "unknown" for profile in values) / max(1, total), 2),
        "unclassified": sum(profile.category_group == "General / Unclassified" for profile in values),
        "unclassified_percent": round(100 * sum(profile.category_group == "General / Unclassified" for profile in values) / max(1, total), 2),
        "no_evidence": sum(not profile.evidence for profile in values),
        "represented_entity": sum(bool(profile.represented_entity) for profile in values),
        "unknown_geography": sum(profile.coverage_type == "unknown" for profile in values),
    }


if __name__ == "__main__":
    main()
