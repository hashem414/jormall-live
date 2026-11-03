from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import HOST, PORT


BASE_URL = f"http://{HOST}:{PORT}"
REPORT_PATH = ROOT / "reports" / "final_runtime_verification.json"


def request(path: str, payload: dict[str, object] | None = None) -> tuple[int, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    with urllib.request.urlopen(urllib.request.Request(BASE_URL + path, data=data, headers=headers), timeout=10) as response:
        body = response.read().decode("utf-8")
        content = json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body
        return response.status, content


def main() -> None:
    root_status, root_body = request("/")
    status_code, status = request("/api/v2/status")
    options_code, options = request("/api/v2/options")
    payload = {
        "campaign_prompt": "consumer electronics for customers in Amman",
        "category": ["Electronics & Technology"],
        "min_quantity": 500,
        "target_quantity": 1000,
        "max_lists": 12,
        "candidate_scope": "direct_adjacent_contextual",
    }
    start_code, started = request("/api/v2/recommend/start", payload)
    job_id = str(started["job_id"])
    final: dict[str, object] = {}
    for _ in range(200):
        poll_code, polled = request(f"/api/v2/recommend/status/{job_id}")
        final = dict(polled)
        if final.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.05)
    result = dict(final.get("result") or {})
    rows = list(result.get("recommended", []))
    checks = {
        "root_http_200": root_status == 200,
        "root_contains_app": "JorMall" in str(root_body),
        "status_http_200": status_code == 200,
        "options_http_200": options_code == 200,
        "start_http_202": start_code == 202,
        "job_completed": final.get("status") == "completed",
        "result_nonnull": bool(result),
        "has_results": bool(rows),
        "category_constraint": all(row.get("Business Category Group") == "Electronics & Technology" for row in rows),
        "minimum_quantity_constraint": all(int(row.get("Quantity", 0)) >= 500 for row in rows),
        "numeric_limit": len(rows) <= 12,
        "target_accounting": result.get("summary", {}).get("target_difference") == result.get("summary", {}).get("total_quantity", 0) - 1000,
        "zero_model_calls": result.get("diagnostics", {}).get("model_call_count") == 0,
    }
    report = {
        "base_url": BASE_URL,
        "tracked_pid": int((ROOT / "data" / "cache" / "hybrid_server.pid").read_text().strip()),
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "status_summary": status.get("summary", {}),
        "option_category_count": len(options.get("categories", [])),
        "job_id": job_id,
        "job_status": final.get("status"),
        "recommended_count": len(rows),
        "result_summary": result.get("summary", {}),
        "diagnostics": result.get("diagnostics", {}),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_checks_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
