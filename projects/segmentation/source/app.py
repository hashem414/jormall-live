from __future__ import annotations

import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

from config import (
    AI_REQUIRED,
    AI_REVIEW_TOP_RESULTS,
    DOTENV_LOADED,
    HOST,
    LLM_INTENT_ENABLED,
    OPENAI_CHAT_MODEL,
    OPENAI_CONFIGURED,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_EMBEDDINGS_ENABLED,
    PORT,
    PROFILES_JSONL_PATH,
    RECOMMENDATION_ENGINE,
)
from engines import HybridEngine, LegacyAdapter, ShadowEngine

from segmentation_engine import (
    build_filter_options,
    canonicalize_campaign_filters,
    catalog_summary,
    filter_from_prompt_heuristic,
    build_company_confirmations,
    build_selection_chart_data,
    compact_company_about,
    load_cached_segments,
    recommend_lists,
    top_chart_data,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DATA_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

DEFAULT_DATA_PATH = DATA_DIR / "default_segments.tsv"
PROCESSED_DATA_PATH = DATA_DIR / "processed_segments.csv"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


def _runtime_status() -> Dict[str, object]:
    if AI_REQUIRED and (not OPENAI_CONFIGURED or not LLM_INTENT_ENABLED):
        mode = "ai_unavailable"
        label = "AI unavailable"
    elif AI_REQUIRED:
        mode = "ai_hybrid_openai"
        label = "AI Hybrid \u00b7 OpenAI"
    else:
        mode = "local_development"
        label = "Local development mode"
    return {
        "runtime_mode": mode,
        "runtime_label": label,
        "dotenv_loaded": DOTENV_LOADED,
        "openai_configured": OPENAI_CONFIGURED,
        "ai_required": AI_REQUIRED,
        "intent_provider": "openai" if LLM_INTENT_ENABLED else "unavailable" if AI_REQUIRED else "local_development",
        "intent_model": OPENAI_CHAT_MODEL if LLM_INTENT_ENABLED else "",
        "embedding_provider": "openai" if OPENAI_EMBEDDINGS_ENABLED else "unavailable" if AI_REQUIRED else "local",
        "embedding_model": OPENAI_EMBEDDING_MODEL if OPENAI_EMBEDDINGS_ENABLED else "",
        "ai_review_enabled": AI_REVIEW_TOP_RESULTS,
    }


print(f"OpenAI configured: {'YES' if OPENAI_CONFIGURED else 'NO'}")
print(f"AI_REQUIRED: {'YES' if AI_REQUIRED else 'NO'}")
print(f"Intent provider: {'OpenAI' if LLM_INTENT_ENABLED else 'Unavailable' if AI_REQUIRED else 'Local development'}")
print(f"Embedding provider: {'OpenAI' if OPENAI_EMBEDDINGS_ENABLED else 'Unavailable' if AI_REQUIRED else 'Local'}")

_catalog_df: pd.DataFrame | None = None
_catalog_path: Path = DEFAULT_DATA_PATH
_last_loaded_at: str | None = None
_last_recommendation: pd.DataFrame | None = None
_last_recommendation_lock = threading.Lock()

_recommendation_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_job_selection_locks: Dict[str, threading.Lock] = {}
_engine_lock = threading.Lock()
_engine_instances: Dict[str, Any] = {}
JOB_TTL_SECONDS = 60 * 60
V2_LOG_DIR = BASE_DIR / "logs"
V2_LOG_DIR.mkdir(exist_ok=True)


def _progress_noop(_percent: int, _message: str) -> None:
    return None


def _set_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        job = _recommendation_jobs.setdefault(job_id, {})
        job.update(updates)
        job["updated_at"] = time.time()


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        for job_id in list(_recommendation_jobs.keys()):
            if _recommendation_jobs[job_id].get("updated_at", 0) < cutoff:
                _recommendation_jobs.pop(job_id, None)
                _job_selection_locks.pop(job_id, None)


def _selection_lock(job_id: str) -> threading.Lock:
    with _jobs_lock:
        return _job_selection_locks.setdefault(job_id, threading.Lock())


def _engine(mode: str | None = None) -> Any:
    selected = "hybrid" if AI_REQUIRED else str(mode or RECOMMENDATION_ENGINE).strip().lower()
    if selected not in {"legacy", "hybrid", "shadow"}:
        selected = "hybrid"
    with _engine_lock:
        if selected not in _engine_instances:
            if selected == "legacy":
                _engine_instances[selected] = LegacyAdapter()
            elif selected == "shadow":
                _engine_instances[selected] = ShadowEngine(BASE_DIR / "reports" / "shadow_comparisons")
            else:
                _engine_instances[selected] = HybridEngine()
        return _engine_instances[selected]


def _v2_recommend(
    payload: Dict[str, Any],
    *,
    include_interaction_state: bool = False,
) -> Dict[str, Any] | tuple[Dict[str, Any], Dict[str, Any] | None]:
    global _last_recommendation
    mode = "hybrid" if AI_REQUIRED else str(payload.get("engine") or RECOMMENDATION_ENGINE).strip().lower()
    result = _engine(mode).recommend(payload)
    interaction_state = result.pop("_interaction_state", None)
    result["engine"] = mode if mode in {"legacy", "hybrid", "shadow"} else "hybrid"
    result.setdefault("ai_note", str(result.get("summary", {}).get("message", "Recommendation completed.")))
    result.setdefault("ai_error", None)
    result.setdefault("company_confirmations", [])
    result.setdefault("enhancements_applied", [])
    result.setdefault("reset_ai_fields", bool(payload.get("reset_ai_fields", False)))
    result.setdefault("selection_chart", [])
    with _last_recommendation_lock:
        _last_recommendation = pd.DataFrame(result.get("recommended", []))
    if include_interaction_state:
        return result, interaction_state
    return result


def load_catalog(force: bool = False) -> pd.DataFrame:
    global _catalog_df, _last_loaded_at
    if force or _catalog_df is None:
        _catalog_df = load_cached_segments(_catalog_path, PROCESSED_DATA_PATH, force=force)
        _last_loaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return _catalog_df


def payload_bool(payload: Dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ["true", "1", "yes", "on"]
    return bool(value)


def payload_int(payload: Dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(str(payload.get(key, default)).replace(",", "") or default)
    except Exception:
        return default


def payload_filter_values(payload: Dict[str, Any], key: str) -> list[str]:
    """Return clean multi-select values from the UI payload.

    The browser sends dropdown filters as tag arrays. Older builds may still send
    a single string, so this accepts both formats. Any/blank values mean no
    manual override.
    """
    value = payload.get(key, "Any")
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]
    cleaned: list[str] = []
    for item in raw_values:
        text = str(item or "").strip()
        if not text or text in ["Any", "NA", "None", "Unknown"]:
            continue
        if text not in cleaned:
            cleaned.append(text)
    return cleaned


def _build_recommendation(payload: Dict[str, Any], progress_cb: Callable[[int, str], None] | None = None) -> Dict[str, Any]:
    """Build one recommendation result.

    This function is shared by the synchronous API and the new background-job
    API. The frontend uses the background API so the browser can show progress
    animation instead of waiting on a single long HTTP request.
    """
    global _last_recommendation
    progress = progress_cb or _progress_noop
    progress(6, "Loading cleaned segment catalog")
    df = load_catalog()
    options_dict = build_filter_options(df)

    prompt = payload.get("campaign_prompt", "") or ""
    ai_filters: Dict[str, Any] = {}
    ai_note = "No intelligent interpretation was needed."
    ai_error = None

    progress(18, "Reading campaign request and suggested filters")
    if prompt.strip():
        ai_filters = filter_from_prompt_heuristic(prompt, options_dict)
        ai_note = "Local keyword interpretation was used by the legacy engine."

    progress(30, "Validating suggested filters against available lists")
    ai_filters = canonicalize_campaign_filters(ai_filters, options_dict)

    local_company = "Any"
    local_companies: list[str] = []
    local_detected: Dict[str, Any] = {}
    if prompt.strip():
        local_detected = canonicalize_campaign_filters(filter_from_prompt_heuristic(prompt, options_dict), options_dict)
        local_company = local_detected.get("desired_company", "Any")
        local_companies = local_detected.get("desired_companies", []) or ([local_company] if local_company not in ["", "Any", "NA"] else [])
    if not ai_filters.get("desired_companies") and local_companies:
        ai_filters["desired_companies"] = local_companies
        ai_filters["desired_company"] = local_companies[0]
    elif ai_filters.get("desired_companies") and local_companies:
        merged = list(ai_filters.get("desired_companies", []))
        for company in local_companies:
            if company not in merged:
                merged.append(company)
        ai_filters["desired_companies"] = merged
        ai_filters["desired_company"] = merged[0]

    # Local deterministic intent acts as a safety net. If the intelligent
    # interpretation misses a clear audience/product phrase, keep the strict
    # logical filter so Max/Enhance does not bring unrelated high-count lists
    # into the result. Product/industry intent also clears accidental company
    # matches such as the word "new" in "new iPhone release".
    for key in [
        "desired_category", "desired_gender", "desired_socioeconomic_class",
        "desired_age_range", "desired_city", "desired_area",
    ]:
        if ai_filters.get(key) in [None, "", "Any", "NA"] and local_detected.get(key) not in [None, "", "Any", "NA"]:
            ai_filters[key] = local_detected.get(key)
    if local_detected.get("strict_logical_match"):
        ai_filters["desired_company"] = "Any"
        ai_filters["desired_companies"] = []
        ai_filters["desired_category"] = local_detected.get("desired_category", ai_filters.get("desired_category", "Any"))
        ai_filters["strict_category_match"] = True
        ai_filters["strict_logical_match"] = True
        ai_filters["logical_intent"] = local_detected.get("logical_intent", "")
        ai_filters["must_have_keywords"] = local_detected.get("must_have_keywords", [])
        ai_filters["avoid_keywords"] = local_detected.get("avoid_keywords", [])
    elif local_detected.get("strict_category_match"):
        ai_filters["strict_category_match"] = True
        ai_filters["audience_intent"] = local_detected.get("audience_intent", "")
        ai_filters["must_have_keywords"] = local_detected.get("must_have_keywords", [])

    suggested_filters = dict(ai_filters)
    reset_ai_fields = payload_bool(payload, "reset_ai_fields", False)

    source_filters = {} if reset_ai_fields else ai_filters
    combined_filters = {
        "desired_company": local_company if local_company not in ["", "Any", "NA"] else source_filters.get("desired_company", "Any"),
        "desired_companies": local_companies if local_companies else source_filters.get("desired_companies", []),
        "desired_category": source_filters.get("desired_category", "Any"),
        "desired_gender": source_filters.get("desired_gender", "Any"),
        "desired_socioeconomic_class": source_filters.get("desired_socioeconomic_class", "Any"),
        "desired_age_range": source_filters.get("desired_age_range", "Any"),
        "desired_city": source_filters.get("desired_city", "Any"),
        "desired_area": source_filters.get("desired_area", "Any"),
        "must_have_keywords": source_filters.get("must_have_keywords", []),
        "avoid_keywords": source_filters.get("avoid_keywords", []),
        "strict_category_match": source_filters.get("strict_category_match", False),
        "strict_logical_match": source_filters.get("strict_logical_match", False),
        "audience_intent": source_filters.get("audience_intent", ""),
        "logical_intent": source_filters.get("logical_intent", ""),
    }
    dropdown_map = {
        "category": "desired_category",
        "gender": "desired_gender",
        "class": "desired_socioeconomic_class",
        "age_range": "desired_age_range",
        "city": "desired_city",
        "area": "desired_area",
    }
    for ui_key, ai_key in dropdown_map.items():
        values = payload_filter_values(payload, ui_key)
        if values:
            # Store arrays when multiple tags are selected. The recommendation
            # engine treats this as OR logic: match any selected category/class/area.
            combined_filters[ai_key] = values if len(values) > 1 else values[0]

    age_min = payload_int(payload, "age_min", 0)
    age_max = payload_int(payload, "age_max", 0)
    full_age_min = payload_int(payload, "full_age_min", 0)
    full_age_max = payload_int(payload, "full_age_max", 0)
    if age_min and age_max and (age_min != full_age_min or age_max != full_age_max):
        lo, hi = sorted([age_min, age_max])
        combined_filters["desired_age_range"] = f"{lo} - {hi}"

    target_quantity = payload_int(payload, "target_quantity", 0)
    # Order Processing should not have to decide backup mechanics. The engine
    # always uses approved unique/special lists, allows controlled class/age
    # expansion only when needed, and keeps AllClasses as backup. The target
    # count is treated as the primary delivery goal.
    allow_class_downgrade = True
    allow_age_extension = True
    use_allclasses_only_as_backup = True
    enhance_count = bool(target_quantity)

    progress(44, "Ranking unique lists and reaching target count")
    result = recommend_lists(
        df,
        combined_filters,
        max_lists=9999 if payload_bool(payload, "max_mode", False) else payload_int(payload, "max_lists", 30),
        min_quantity=payload_int(payload, "min_quantity", 0),
        target_quantity=target_quantity,
        enhance_count=enhance_count,
        include_unique_lists=True,
        allow_class_downgrade=allow_class_downgrade,
        allow_age_extension=allow_age_extension,
        use_allclasses_only_as_backup=use_allclasses_only_as_backup,
    )

    with _last_recommendation_lock:
        _last_recommendation = pd.DataFrame(result["recommended"])

    progress(68, "Preparing company branch/location confirmation")
    company_list = combined_filters.get("desired_companies", []) or ([combined_filters.get("desired_company", "Any")] if combined_filters.get("desired_company", "Any") not in ["", "Any", "NA"] else [])
    result["company_confirmations"] = build_company_confirmations(
        df,
        company_list,
        result.get("recommended", []),
        campaign_prompt=prompt,
        use_openai=False,
    )
    result["company_confirmation"] = result["company_confirmations"][0] if result["company_confirmations"] else {"available": False, "company": "Any", "about": "No company name was detected in the request."}

    about_by_company: Dict[str, str] = {}
    for profile in result.get("company_confirmations", []):
        company_name = str(profile.get("company", "")).strip()
        if company_name:
            about_by_company[company_name] = compact_company_about(profile)
    if about_by_company and result.get("recommended"):
        for row in result["recommended"]:
            row_company = str(row.get("Company", "")).strip()
            if row_company in about_by_company:
                row["About"] = about_by_company[row_company]

    progress(90, "Preparing grid and chart data")
    result["suggested_filters"] = suggested_filters
    result["interpreted_filters"] = combined_filters
    result["reset_ai_fields"] = reset_ai_fields
    result["ai_note"] = ai_note
    result["ai_error"] = ai_error
    result["selection_chart"] = build_selection_chart_data(pd.DataFrame(result.get("recommended", [])))
    progress(100, "Recommendation ready")
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    df = load_catalog()
    summary = catalog_summary(df)
    return jsonify({
        "ok": True,
        **_runtime_status(),
        "recommendation_engine": RECOMMENDATION_ENGINE,
        "loaded_at": _last_loaded_at,
        "summary": summary,
        "charts": {
            "categories": top_chart_data(df, "Category", 10),
            "classes": top_chart_data(df, "Class", 10),
            "cities": top_chart_data(df, "City / Coverage", 10),
        },
    })


@app.route("/api/options")
def options():
    df = load_catalog()
    return jsonify(build_filter_options(df))


@app.route("/api/v2/options")
def options_v2():
    if RECOMMENDATION_ENGINE != "hybrid":
        return options()
    hybrid = _engine("hybrid")
    profiles = list(hybrid.profiles.values())
    ages_min = [profile.age_min for profile in profiles if profile.age_min is not None]
    ages_max = [profile.age_max for profile in profiles if profile.age_max is not None]

    def values(items: Any) -> list[str]:
        return ["Any", *sorted({item for item in items if item})]

    return jsonify({
        "categories": values(profile.category_group for profile in profiles),
        "genders": values(profile.gender for profile in profiles),
        "classes": values(profile.economic_class for profile in profiles),
        "cities": values(
            city
            for profile in profiles
            for city in (
                ["All Jordan"]
                if profile.coverage_type in {"national", "all_jordan"}
                else profile.cities
            )
        ),
        "areas": values(area for profile in profiles for area in profile.areas),
        "age_bounds": {"min": min(ages_min, default=17), "max": max(ages_max, default=80)},
    })


@app.route("/api/v2/status")
def status_v2():
    if RECOMMENDATION_ENGINE != "hybrid" and not AI_REQUIRED:
        return status()
    hybrid = _engine("hybrid")
    profiles = list(hybrid.profiles.values())
    eligible = [profile for profile in profiles if profile.eligible]

    def quantity_chart(values: Any) -> list[dict[str, object]]:
        totals: Dict[str, int] = {}
        for label, quantity in values:
            if label:
                totals[label] = totals.get(label, 0) + int(quantity)
        return [{"label": label, "value": value} for label, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:10]]

    return jsonify({
        "ok": True,
        **_runtime_status(),
        "recommendation_engine": RECOMMENDATION_ENGINE,
        "loaded_at": datetime.fromtimestamp(PROFILES_JSONL_PATH.stat().st_mtime).isoformat(timespec="seconds"),
        "summary": {
            "total_rows": len(profiles) + hybrid.duplicates_suppressed,
            "ready_lists": len(eligible),
            "total_quantity_ready": sum(profile.quantity for profile in eligible),
            "raw_categories": len({profile.original_category for profile in profiles if profile.original_category}),
            "category_groups": len({profile.category_group for profile in profiles if profile.category_group}),
            "duplicate_except_date_rows": hybrid.duplicates_suppressed,
            "source_excluded_lists": len(profiles) - len(eligible),
        },
        "charts": {
            "categories": quantity_chart((profile.category_group, profile.quantity) for profile in eligible),
            "classes": quantity_chart((profile.economic_class, profile.quantity) for profile in eligible),
            "cities": quantity_chart((city, profile.quantity) for profile in eligible for city in profile.cities),
        },
    })


@app.route("/api/recommend", methods=["POST"])
def recommend():
    payload = request.get_json(silent=True) or {}
    return jsonify(_v2_recommend(payload))


@app.route("/api/recommend/start", methods=["POST"])
def recommend_start():
    _prune_jobs()
    payload = request.get_json(silent=True) or {}
    job_id = uuid.uuid4().hex
    _set_job(job_id, status="queued", progress=1, message="Queued recommendation job", result=None, error=None, created_at=time.time())

    def worker() -> None:
        try:
            _set_job(job_id, status="running", progress=4, message="Understanding campaign with OpenAI")
            result = _v2_recommend(payload)
            _set_job(job_id, status="done", progress=100, message="Recommendation ready", result=result)
        except Exception as exc:
            _set_job(job_id, status="error", progress=100, message="Recommendation failed", error=str(exc), traceback=traceback.format_exc())

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/recommend/status/<job_id>")
def recommend_status(job_id: str):
    with _jobs_lock:
        job = dict(_recommendation_jobs.get(job_id) or {})
    if not job:
        return jsonify({"ok": False, "error": "Recommendation job not found or expired."}), 404
    # Do not expose the internal traceback to the browser by default.
    job.pop("traceback", None)
    job["ok"] = True
    return jsonify(job)


@app.route("/api/v2/recommend/start", methods=["POST"])
def recommend_v2_start():
    _prune_jobs()
    payload = request.get_json(silent=True) or {}
    job_id = uuid.uuid4().hex
    _selection_lock(job_id)
    _set_job(job_id, api_version="v2", status="queued", progress=1, message="Queued recommendation job", result=None, error=None, created_at=time.time())

    def worker() -> None:
        try:
            _set_job(job_id, status="processing", progress=10, message="Understanding campaign with OpenAI")
            result, interaction_state = _v2_recommend(payload, include_interaction_state=True)
            if result is None:
                raise RuntimeError("Recommendation engine returned no result")
            result["job_id"] = job_id
            _set_job(
                job_id,
                status="completed",
                progress=100,
                message="Recommendation ready",
                result=result,
                error=None,
                _interaction_state=interaction_state,
            )
        except Exception as exc:
            trace = traceback.format_exc()
            log_path = V2_LOG_DIR / f"v2_job_{job_id}.log"
            log_path.write_text(trace, encoding="utf-8")
            _set_job(
                job_id,
                status="failed",
                progress=100,
                message="Recommendation failed",
                result=None,
                error={"message": str(exc), "log_reference": log_path.name},
            )

    threading.Thread(target=worker, daemon=True, name=f"recommend-v2-{job_id[:8]}").start()
    return jsonify({"ok": True, "job_id": job_id, "status": "queued"}), 202


@app.route("/api/v2/recommend/status/<job_id>")
def recommend_v2_status(job_id: str):
    with _jobs_lock:
        job = dict(_recommendation_jobs.get(job_id) or {})
    if not job or job.get("api_version") != "v2":
        return jsonify({"ok": False, "error": {"message": "Recommendation job not found or expired."}}), 404
    job.pop("traceback", None)
    job.pop("_interaction_state", None)
    job["ok"] = True
    return jsonify(job)


def _selection_payload(result: Dict[str, Any], *, stale: bool = False) -> Dict[str, Any]:
    diagnostics = result.get("diagnostics", {})
    return {
        "ok": True,
        "stale": stale,
        "revision": int(result.get("result_state", {}).get("revision", 0)),
        "recommendations": result.get("recommended", []),
        "summary": result.get("summary", {}),
        "result_category_groups": result.get("result_category_groups", []),
        "result_state": result.get("result_state", {}),
        "interaction_diagnostics": diagnostics.get("interaction", {}),
    }


@app.route("/api/v2/recommend/jobs/<job_id>/selection", methods=["POST"])
def update_recommendation_selection(job_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        revision = max(0, int(payload.get("revision", 0)))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": {"message": "Revision must be an integer."}}), 400
    excluded_ids = payload.get("excluded_ids", [])
    selected_ids = payload.get("selected_ids", [])
    if not isinstance(excluded_ids, list) or not isinstance(selected_ids, list):
        return jsonify({"ok": False, "error": {"message": "Selection IDs must be arrays."}}), 400

    with _selection_lock(job_id):
        with _jobs_lock:
            job = _recommendation_jobs.get(job_id)
            if not job or job.get("api_version") != "v2":
                return jsonify({"ok": False, "error": {"message": "Recommendation job not found or expired."}}), 404
            if job.get("status") != "completed" or not job.get("_interaction_state"):
                return jsonify({"ok": False, "error": {"message": "Recommendation result is not ready for interaction."}}), 409
            state = job["_interaction_state"]
            current_result = job["result"]

        current_revision = int(state.get("revision", 0))
        if revision <= current_revision:
            return jsonify(_selection_payload(current_result, stale=revision < current_revision))

        public, updated_state, _derived = _engine("hybrid").recompute_interaction_state(
            state,
            excluded_ids=[str(value) for value in excluded_ids],
            selected_ids=[str(value) for value in selected_ids],
            revision=revision,
            auto_select_replacements=bool(payload.get("auto_select_replacements", True)),
        )
        result = dict(current_result)
        result["recommended"] = public["recommendations"]
        result["summary"] = {**result.get("summary", {}), **public["summary"]}
        result["result_category_groups"] = public["result_category_groups"]
        result["result_state"] = public["result_state"]
        diagnostics = dict(result.get("diagnostics", {}))
        diagnostics["interaction"] = public["interaction_diagnostics"]
        diagnostics["returned_count"] = len(public["recommendations"])
        diagnostics["returned_profiles"] = len(public["recommendations"])
        diagnostics["returned_candidates"] = len(public["recommendations"])
        target = dict(diagnostics.get("target", {}))
        target.update({
            "qualified_before_target": public["summary"]["available_recommendable_lists"],
            "selected_after_target": public["summary"]["active_recommendation_list_count"],
            "gross_selected_quantity": public["summary"]["active_recommended_quantity"],
            "reached": public["summary"]["target_reached"],
            "status": public["summary"]["target_status"],
            "overshoot": public["summary"]["target_overshoot"],
            "shortage": public["summary"]["target_shortage"],
        })
        diagnostics["target"] = target
        result["diagnostics"] = diagnostics

        with _jobs_lock:
            live_job = _recommendation_jobs.get(job_id)
            if not live_job:
                return jsonify({"ok": False, "error": {"message": "Recommendation job expired."}}), 404
            live_job["_interaction_state"] = updated_state
            live_job["result"] = result
            live_job["updated_at"] = time.time()
        with _last_recommendation_lock:
            global _last_recommendation
            _last_recommendation = pd.DataFrame(public["recommendations"])
        return jsonify(_selection_payload(result))


@app.route("/api/v2/recommend/jobs/<job_id>/export")
def export_current_recommendation(job_id: str):
    with _selection_lock(job_id):
        with _jobs_lock:
            job = _recommendation_jobs.get(job_id)
            if not job or job.get("api_version") != "v2" or not job.get("_interaction_state"):
                return jsonify({"ok": False, "error": {"message": "Recommendation job not found or expired."}}), 404
            state = job["_interaction_state"]
        try:
            requested_revision = int(request.args.get("revision", state.get("revision", 0)))
        except (TypeError, ValueError):
            requested_revision = int(state.get("revision", 0))
        if requested_revision > int(state.get("revision", 0)):
            return jsonify({"ok": False, "error": {"message": "Selection state is still synchronizing."}}), 409
        selected = set(state.get("selected_ids", []))
        excluded = set(state.get("excluded_ids", []))
        rows = [
            row for row in state.get("serialized_active", [])
            if row.get("List ID") in selected and row.get("List ID") not in excluded
        ]
        if not rows:
            return jsonify({"ok": False, "error": {"message": "No current lists are selected for export."}}), 400
        path = EXPORT_DIR / (
            f"campaign_selected_lists_{job_id[:8]}_r{int(state.get('revision', 0))}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
        return send_file(path, as_attachment=True, download_name=path.name)


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "openai_configured": OPENAI_CONFIGURED})


@app.route("/api/export/recommendation")
def export_recommendation():
    with _last_recommendation_lock:
        rec = None if _last_recommendation is None else _last_recommendation.copy()
    if rec is None or rec.empty:
        return jsonify({"ok": False, "error": "No recommendation available to export yet."}), 400
    path = EXPORT_DIR / f"campaign_recommended_lists_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    rec.to_csv(path, index=False, encoding="utf-8-sig")
    return send_file(path, as_attachment=True, download_name=path.name)


@app.route("/api/export/category-clusters")
def export_category_clusters():
    df = load_catalog()
    path = EXPORT_DIR / f"business_category_cluster_mapping_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    if "Original Category" in df.columns and "Business Category Group" in df.columns:
        mapping = (
            df[df["Ready for Recommendation"]]
            .groupby(["Business Category Group", "Original Category"], dropna=False)
            .agg(Lists=("List ID", "count"), Quantity=("Quantity", "sum"))
            .reset_index()
            .sort_values(["Business Category Group", "Quantity"], ascending=[True, False])
        )
    else:
        mapping = df[["Category"]].drop_duplicates().rename(columns={"Category": "Business Category Group"})
    mapping.to_csv(path, index=False, encoding="utf-8-sig")
    return send_file(path, as_attachment=True, download_name=path.name)


@app.route("/api/export/catalog")
def export_catalog():
    df = load_catalog()
    path = EXPORT_DIR / f"clean_segment_catalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    export_cols = [
        "List ID", "List Name", "Company", "About", "Business Category Group", "Original Category",
        "Category", "Gender", "Class", "Age Range", "City / Coverage", "Area", "Quantity",
        "Created Date", "Unique / Special List", "Exclusive Data", "Ready for Recommendation",
        "Duplicate Except Date", "Preferred Duplicate Version", "Source Eligible", "Source Exclusion Reason", "Staleness Rule",
    ]
    df[export_cols].to_csv(path, index=False, encoding="utf-8-sig")
    return send_file(path, as_attachment=True, download_name=path.name)


@app.route("/api/export/source-exclusions")
def export_source_exclusions():
    df = load_catalog()
    path = EXPORT_DIR / f"dropped_source_lists_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    if "Source Eligible" in df.columns:
        dropped = df[~df["Source Eligible"]].copy()
    else:
        dropped = pd.DataFrame()
    export_cols = [
        "List ID", "List Name", "Company", "Business Category Group", "Original Category",
        "Gender", "Class", "Age Range", "City / Coverage", "Area", "Quantity",
        "Created Date", "Source Exclusion Reason", "Ready for Recommendation",
    ]
    if dropped.empty:
        dropped = pd.DataFrame(columns=export_cols)
    else:
        dropped = dropped[[c for c in export_cols if c in dropped.columns]]
    dropped.to_csv(path, index=False, encoding="utf-8-sig")
    return send_file(path, as_attachment=True, download_name=path.name)


if __name__ == "__main__":
    # threaded=True allows the browser to poll job status while a recommendation
    # runs in a background thread.
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
