from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = f"http://127.0.0.1:{os.getenv('PORT', '5002')}"
PROMPTS = [
    "solar panels to factories and homeowners",
    "ألواح شمسية للمصانع",
    "mobile telecom package",
    "mobile cranes for construction",
    "Not hair dryers - industrial dryers",
]


def request(path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    with urllib.request.urlopen(urllib.request.Request(BASE_URL + path, data=data, headers=headers), timeout=30) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def recommend(prompt: str) -> dict[str, object]:
    status, started = request("/api/v2/recommend/start", {"campaign_prompt": prompt, "max_lists": 10})
    if status != 202:
        raise RuntimeError(f"Unexpected start status {status}")
    for _ in range(300):
        _status, job = request(f"/api/v2/recommend/status/{started['job_id']}")
        if job["status"] == "completed":
            result = job["result"]
            return {"query": prompt, "recommendations": len(result["recommended"]), "model_calls": result["diagnostics"]["model_call_count"], "zero_evidence_leakage": result["diagnostics"]["zero_evidence_leakage"], "total_ms": result["timings"]["total_ms"]}
        if job["status"] == "failed":
            raise RuntimeError(str(job))
        time.sleep(0.05)
    raise TimeoutError(prompt)


def main() -> None:
    rows = [recommend(prompt) for prompt in PROMPTS]
    report = {"base_url": BASE_URL, "checks_pass": all(row["recommendations"] > 0 and row["model_calls"] == 0 and row["zero_evidence_leakage"] == 0 for row in rows), "requests": rows}
    output = ROOT / "reports" / "smart_rebuild" / "final_http_validation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
