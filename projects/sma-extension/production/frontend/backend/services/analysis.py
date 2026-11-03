from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable


def as_number(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else 0.0
    text = str(value or "").strip().replace(",", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(text) if text not in {"", "-", "."} else 0.0
    except ValueError:
        return 0.0


def compact_json(value: Any, max_chars: int = 220_000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…[truncated]"


def count_rows(payload: dict[str, Any]) -> int:
    if isinstance(payload.get("rows"), list):
        return len(payload["rows"])
    category = payload.get("categoryDeliveryData")
    if isinstance(category, dict):
        rows = category.get("filteredRows") or category.get("rows")
        if isinstance(rows, list):
            return len(rows)
    notes = payload.get("notesData")
    if isinstance(notes, dict) and isinstance(notes.get("notes"), list):
        return len(notes["notes"])
    return 0


def _pick(row: dict[str, Any], names: Iterable[str]) -> Any:
    lower = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name in row:
            return row[name]
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def _risk_labels(row: dict[str, Any]) -> list[str]:
    raw = _pick(row, ["risks", "flags", "tasks", "issues"])
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [part.strip() for part in re.split(r"[,;|\n]+", raw) if part.strip()]
    return []


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [row for row in rows if isinstance(row, dict)]
    risk_counts: Counter[str] = Counter()
    total_balance = 0.0
    total_delivery = 0.0
    total_target = 0.0
    named: list[tuple[str, float, list[str]]] = []

    for row in normalized:
        risks = _risk_labels(row)
        risk_counts.update(risks)
        balance = as_number(_pick(row, ["totalBalance", "totalBalanceNumber", "currentPb", "pb", "balance"]))
        delivery = as_number(_pick(row, ["smsDeliveryThisMonth", "smsDeliveryThisMonthNumber", "delivery", "delivered"]))
        target = as_number(_pick(row, ["smsTargetDelivery", "smsTargetDeliveryNumber", "target", "monthlyTarget"]))
        total_balance += balance
        total_delivery += delivery
        total_target += target
        name = str(_pick(row, ["companyName", "name", "company", "customerName"]) or "Unnamed company")
        named.append((name, balance, risks))

    highest_balances = sorted(named, key=lambda item: item[1], reverse=True)[:5]
    risky = sorted(named, key=lambda item: (len(item[2]), item[1]), reverse=True)[:5]
    achievement = (total_delivery / total_target * 100.0) if total_target > 0 else None

    return {
        "rowCount": len(normalized),
        "totalBalance": round(total_balance, 2),
        "totalDelivery": round(total_delivery, 2),
        "totalTarget": round(total_target, 2),
        "achievementPercent": round(achievement, 1) if achievement is not None else None,
        "riskCounts": dict(risk_counts.most_common(12)),
        "highestBalances": [{"company": n, "balance": round(b, 2)} for n, b, _ in highest_balances],
        "highestRisk": [{"company": n, "risks": r} for n, _, r in risky if r],
    }


def _fmt_number(value: float) -> str:
    return f"{value:,.0f}"


def local_chat_answer(payload: dict[str, Any]) -> str:
    screen = str(payload.get("screen") or "SMA report")
    question = str(payload.get("question") or "").strip()
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if not rows and isinstance(payload.get("categoryDeliveryData"), dict):
        category = payload["categoryDeliveryData"]
        rows = category.get("filteredRows") or category.get("rows") or []
    rows = [row for row in rows if isinstance(row, dict)]
    summary = summarize_rows(rows)

    lines = ["### SMA report summary"]
    lines.append(f"- Screen: **{screen}**")
    lines.append(f"- Records analyzed: **{summary['rowCount']}**")
    if summary["totalTarget"] or summary["totalDelivery"]:
        lines.append(f"- Delivery: **{_fmt_number(summary['totalDelivery'])}** of **{_fmt_number(summary['totalTarget'])}** target")
    if summary["achievementPercent"] is not None:
        lines.append(f"- Overall achievement: **{summary['achievementPercent']}%**")
    if summary["totalBalance"]:
        lines.append(f"- Total detected balance: **{_fmt_number(summary['totalBalance'])} SMS**")

    if summary["riskCounts"]:
        risks = ", ".join(f"{name}: {count}" for name, count in list(summary["riskCounts"].items())[:6])
        lines.extend(["", "### Main risks", f"- {risks}"])

    if summary["highestRisk"]:
        lines.append("")
        lines.append("### Immediate follow-up")
        for item in summary["highestRisk"][:5]:
            lines.append(f"- **{item['company']}** — {', '.join(item['risks'])}")

    if question:
        lines.extend([
            "",
            "### Requested analysis",
            f"The gateway is online, but no OpenAI API key is configured. The local analysis above is based on the current dataset. Configure `OPENAI_API_KEY` to receive a full natural-language answer to: **{question}**",
        ])
    return "\n".join(lines)


def _notes_list(notes_data: dict[str, Any]) -> list[dict[str, Any]]:
    notes = notes_data.get("notes")
    return [note for note in notes if isinstance(note, dict)] if isinstance(notes, list) else []


def local_notes_summary(notes_data: dict[str, Any]) -> dict[str, Any]:
    notes = _notes_list(notes_data)
    latest = notes[0] if notes else {}
    company = (
        notes_data.get("companyName")
        or notes_data.get("company")
        or latest.get("companyName")
        or "the client"
    )
    latest_text = str(latest.get("notice") or latest.get("note") or latest.get("text") or "No recent note was detected.").strip()

    risk_terms = {
        "No recent contact": r"no answer|not responding|unreachable|no response|to call",
        "Payment or balance issue": r"payment|invoice|collection|balance|expired",
        "Low usage": r"not using|low usage|slow sent|no delivery|inactive",
        "Technical concern": r"technical|error|issue|problem|failed|delay",
        "Commercial resistance": r"not interested|competitor|another company|refused",
    }
    corpus = " ".join(str(n.get("notice") or n.get("note") or n.get("text") or "") for n in notes).lower()
    risks = [label for label, pattern in risk_terms.items() if re.search(pattern, corpus)]
    if not risks and not notes:
        risks = ["Insufficient notes for a confident assessment"]

    departments = notes_data.get("departmentMap") or notes_data.get("departments") or notes_data.get("categories") or {}
    account_facts = {
        "company": company,
        "notes_count": len(notes),
        "latest_note_date": latest.get("date") or latest.get("createdAt") or latest.get("noteDate") or "Not detected",
    }
    return {
        "executive_summary": f"{company} has {len(notes)} detected note(s). The latest recorded update is: {latest_text}",
        "latest_updates_summary": latest_text,
        "account_facts": account_facts,
        "risks": risks,
        "next_best_action": "Confirm the current account status, assign one owner, contact the client with a specific campaign or service-use proposal, and record a dated next step.",
        "department_summary": departments,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def local_followup(payload: dict[str, Any]) -> str:
    company = str(payload.get("companyName") or payload.get("company") or "the client")
    purpose = str(payload.get("purpose") or payload.get("question") or "review the account and agree on the next campaign")
    return (
        f"Hello {company},\n\n"
        f"We are following up to {purpose}. Our team can help review the available SMS balance, prepare a suitable campaign, and support execution and reporting. "
        "Please share a convenient time for a brief call.\n\nBest regards,\nJorMall Team"
    )
