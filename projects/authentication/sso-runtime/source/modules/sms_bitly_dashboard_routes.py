# sms_bitly_dashboard_routes.py
# Flask backend for Bitly-style dashboard
# Route name: /sms-bitly-dashboard (page) and JSON APIs under /api/

import os
import json
import math
import requests
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Blueprint, current_app, jsonify, render_template, request, abort, Flask, Response, request, jsonify, send_from_directory, session, abort, send_file, render_template
from dotenv import load_dotenv
# add this import near the top
from urllib.parse import quote

# --- Config ---
load_dotenv()
BITLY_TOKEN = os.getenv("BITLY_API_KEY")
BITLY_LOG_DIR = os.path.join("exports", "bitly_logs")
TIMEZONE = ZoneInfo("Asia/Amman")
DASHBOARD_DEFAULT_DAYS = 30

bp = Blueprint("sms_bitly_dashboard", __name__)


@bp.before_request
def require_authenticated_session():
    if not session.get("logged_in") or not session.get("username"):
        return jsonify({"error": "Not authorized"}), 401

# --- Simple in-memory cache to respect Bitly rate limits ---
_cached = {
    "dashboard": {"expires": datetime.min.replace(tzinfo=TIMEZONE), "days": None, "payload": None},
    # per-link cache map: bitlink -> {expires, days, payload}
    "per_link": {}
}
CACHE_TTL_SECONDS = 0 * 60  # 5 minutes


def _now():
    return datetime.now(TIMEZONE)


def _auth_headers():
    if not BITLY_TOKEN:
        raise RuntimeError("BITLY_API_KEY env var not set")
    return {
        "Authorization": f"Bearer {BITLY_TOKEN}",
        "Content-Type": "application/json",
    }


# --- Utilities ---

def _iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _daterange_days(days: int):
    # returns list of date strings for the last `days` days inclusive of today
    end = _now().date()
    return [str(end - timedelta(days=i)) for i in range(days - 1, -1, -1)]


def _safe_load(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _list_bitlink_logs():
    if not os.path.isdir(BITLY_LOG_DIR):
        return []
    files = [
        os.path.join(BITLY_LOG_DIR, f)
        for f in os.listdir(BITLY_LOG_DIR)
        if f.endswith(".json") and not f.endswith("_ERROR.json")
    ]
    files.sort(reverse=True)
    return files


def _collect_bitlinks_from_logs():
    bitlinks = {}
    for path in _list_bitlink_logs():
        data = _safe_load(path)
        if not data:
            continue

        # Try several places for id/link
        bitlink = (
            data.get("bitly_id")
            or data.get("id")
            or (data.get("bitly_response") or {}).get("id")
        )
        short_url = (
            data.get("short_url")
            or (data.get("bitly_response") or {}).get("link")
        )

        if not bitlink:
            if short_url:
                bitlink = short_url.split("//", 1)[1] if "://" in short_url else short_url

        if not bitlink:
            continue

        # normalize short_url if missing
        if not short_url:
            short_url = "https://" + bitlink

        if bitlink not in bitlinks:  # keep newest
            bitlinks[bitlink] = {
                "bitlink": bitlink,
                "short_url": short_url,
                "label": data.get("label") or data.get("campaign_name") or "",
                "company_name": data.get("company_name") or data.get("companyName") or "",
                "created_by": data.get("created_by") or data.get("user") or "",
                "created_at": data.get("timestamp_iso") or data.get("created_at"),
                "log_path": path,
            }
    return bitlinks

# place this helper under Utilities (before Bitly API calls)

def _enc(bitlink: str) -> str:
    """
    URL-encode a bitlink for use in Bitly API paths.
    Accepts 'bit.ly/abc123' or full 'https://bit.ly/abc123'.
    """
    if bitlink.startswith("http://") or bitlink.startswith("https://"):
        bitlink = bitlink.split("//", 1)[1]  # keep domain/path only
    return quote(bitlink, safe="")  # encode '/' too


# --- Bitly API calls ---

BASE = "https://api-ssl.bitly.com/v4"

def _bitly_now_str():
    # Example: 2025-08-10T14:34:14+0300  (offset WITHOUT colon)
    return _now().strftime("%Y-%m-%dT%H:%M:%S%z")

def _bitly_get_clicks_timeseries(bitlink: str, days: int):
    params = {
        "unit": "day",
        "units": days,
        "unit_reference": _bitly_now_str(),   # <- was isoformat
    }
    url = f"{BASE}/bitlinks/{_enc(bitlink)}/referrers"
    r = requests.get(url, headers=_auth_headers(), params=params, timeout=15)
    r.raise_for_status()
    js = r.json() or {}
    # Normalize into ordered date->clicks map covering all days
    dates = _daterange_days(days)
    by_date = OrderedDict((d, 0) for d in dates)
    for row in js.get("link_clicks", []):
        # Bitly returns ISO date string under key 'date'
        day = row.get("date", "")[0:10]
        if day in by_date:
            by_date[day] = int(row.get("clicks", 0))
    return by_date


def _bitly_get_referrers(bitlink: str, days: int):
    base_params = {
        "unit": "day",
        "units": days,
        "size": 100,
    }
    url = f"{BASE}/bitlinks/{_enc(bitlink)}/referrers"

    # 1st try WITH unit_reference (correctly formatted)
    params = dict(base_params)
    params["unit_reference"] = _bitly_now_str()
    try:
        r = requests.get(url, headers=_auth_headers(), params=params, timeout=15)
        r.raise_for_status()
        js = r.json() or {}
    except requests.HTTPError as e:
        # If it's a 400, retry WITHOUT unit_reference (some links/tiers reject it)
        if getattr(e.response, "status_code", None) == 400:
            r = requests.get(url, headers=_auth_headers(), params=base_params, timeout=15)
            r.raise_for_status()
            js = r.json() or {}
        else:
            raise

    refs = defaultdict(int)
    for m in js.get("metrics", []):
        refs[str(m.get("value") or "unknown")] += int(m.get("clicks", 0))
    return dict(refs)


# --- Aggregation & KPIs ---

def _kpis_from_series(series_map: OrderedDict):
    vals = list(series_map.values())
    total = sum(vals)
    last7 = sum(vals[-7:]) if len(vals) >= 7 else sum(vals)
    prev7 = sum(vals[-14:-7]) if len(vals) >= 14 else 0
    if prev7 == 0:
        wow = None  # undefined
    else:
        wow = ((last7 - prev7) / prev7) * 100.0
    return total, last7, prev7, wow


def _build_dashboard(days: int):
    bitlinks = _collect_bitlinks_from_logs()
    if not bitlinks:
        return {
            "generated_at": _now().isoformat(timespec="seconds"),
            "days": days,
            "timeseries_all": [],
            "referrers_pie": [],
            "top_links": [],
        }

    # Aggregate
    dates = _daterange_days(days)
    all_series = OrderedDict((d, 0) for d in dates)
    ref_total = defaultdict(int)
    top_links = []

    for bl, meta in bitlinks.items():
        try:
            s_map = _bitly_get_clicks_timeseries(bl, days)
            for d, c in s_map.items():
                all_series[d] += int(c)

            refs = _bitly_get_referrers(bl, days)
            for name, c in refs.items():
                ref_total[name] += int(c)

            total, last7, prev7, wow = _kpis_from_series(s_map)
            top_links.append({
                "bitlink": bl,
                "short_url": meta.get("short_url"),
                "label": meta.get("label"),
                "company_name": meta.get("company_name"),
                "created_by": meta.get("created_by"),
                "created_at": meta.get("created_at"),
                "total_clicks": total,
                "last7": last7,
                "prev7": prev7,
                "wow_change_pct": wow,
                "series": list({"date": d, "clicks": s_map[d]} for d in s_map.keys()),
            })
        except requests.HTTPError as e:
            current_app.logger.warning(f"Bitly API error for {bl}: {e}")
        except Exception as e:
            current_app.logger.exception(f"Unexpected error for {bl}: {e}")

    top_links.sort(key=lambda x: x.get("total_clicks", 0), reverse=True)

    payload = {
        "generated_at": _now().isoformat(timespec="seconds"),
        "days": days,
        "timeseries_all": [{"date": d, "clicks": all_series[d]} for d in all_series.keys()],
        "referrers_pie": [{"referrer": k or "unknown", "clicks": v} for k, v in sorted(ref_total.items(), key=lambda kv: kv[1], reverse=True)],
        "top_links": top_links,
    }
    return payload


# --- Routes ---

@bp.route("/sms-bitly-dashboard")
def sms_bitly_dashboard_page():
    static_dir = os.path.join(current_app.root_path, 'static')
    return send_from_directory(static_dir, 'sms_bitly_dashboard.html')


@bp.route("/api/sms-bitly-dashboard")
def sms_bitly_dashboard_data():
    try:
        days = int(request.args.get("days", DASHBOARD_DEFAULT_DAYS))
    except ValueError:
        days = DASHBOARD_DEFAULT_DAYS

    # cache
    c = _cached["dashboard"]
    if c["payload"] is not None and c["days"] == days and c["expires"] > _now():
        return jsonify(c["payload"])  # cached

    payload = _build_dashboard(days)
    _cached["dashboard"] = {"expires": _now() + timedelta(seconds=CACHE_TTL_SECONDS), "days": days, "payload": payload}
    return jsonify(payload)


@bp.route("/api/sms-bitly-link/<path:bitlink>")
def sms_bitly_link_detail(bitlink):
    try:
        days = int(request.args.get("days", DASHBOARD_DEFAULT_DAYS))
    except ValueError:
        days = DASHBOARD_DEFAULT_DAYS

    # per-link cache
    c = _cached["per_link"].get(bitlink)
    if c and c["days"] == days and c["expires"] > _now():
        return jsonify(c["payload"])  # cached

    # lookup meta from logs
    meta = _collect_bitlinks_from_logs().get(bitlink)
    if not meta:
        abort(404, description="Bitlink not found in logs")

    # build
    series = _bitly_get_clicks_timeseries(bitlink, days)
    total, last7, prev7, wow = _kpis_from_series(series)
    refs = _bitly_get_referrers(bitlink, days)

    payload = {
        "bitlink": bitlink,
        "short_url": meta.get("short_url"),
        "label": meta.get("label"),
        "company_name": meta.get("company_name"),
        "created_by": meta.get("created_by"),
        "created_at": meta.get("created_at"),
        "series": [{"date": d, "clicks": series[d]} for d in series.keys()],
        "total_clicks": total,
        "last7": last7,
        "prev7": prev7,
        "wow_change_pct": wow,
        "referrers": refs,
    }

    _cached["per_link"][bitlink] = {"expires": _now() + timedelta(seconds=CACHE_TTL_SECONDS), "days": days, "payload": payload}
    return jsonify(payload)

@bp.route("/api/sms-bitly-debug")
def sms_bitly_debug():
    root = os.path.join(current_app.root_path, BITLY_LOG_DIR) \
           if not os.path.isabs(BITLY_LOG_DIR) else BITLY_LOG_DIR
    seen = []
    reasons = []
    files = []
    if os.path.isdir(root):
        for dirpath, _, filenames in os.walk(root):  # recurse
            for f in filenames:
                if f.endswith(".json") and not f.endswith("_ERROR.json"):
                    files.append(os.path.join(dirpath, f))
    else:
        reasons.append(f"Directory not found: {root}")

    bitlinks = []
    for p in sorted(files, reverse=True):
        data = _safe_load(p)
        if not data:
            reasons.append(f"Unreadable JSON: {p}")
            continue
        bl = data.get("bitly_id") or data.get("id")
        if not bl:
            # try from short_url or nested bitly_response
            su = data.get("short_url") or (data.get("bitly_response") or {}).get("link")
            if su and "://" in su:
                bl = su.split("//", 1)[1]
            elif su:
                bl = su
        if not bl:
            reasons.append(f"No bitlink keys in: {p}")
            continue
        bitlinks.append({"bitlink": bl, "path": p})
        seen.append(p)

    return jsonify({
        "BITLY_LOG_DIR": BITLY_LOG_DIR,
        "absolute_dir": root,
        "total_files": len(files),
        "seen_valid_bitlinks": len(bitlinks),
        "bitlinks": bitlinks[:20],  # sample
        "reasons": reasons[:20],
    })

# --- Integration helper ---
# In your app factory or main app file:
# from sms_bitly_dashboard_routes import bp as sms_bitly_bp
# app.register_blueprint(sms_bitly_bp)
