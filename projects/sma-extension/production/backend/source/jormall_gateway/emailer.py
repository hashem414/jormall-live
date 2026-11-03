from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from .config import Settings


def send_sales_priority(settings: Settings, payload: dict[str, Any]) -> int:
    if not settings.email_enabled:
        raise RuntimeError("Email notifications are not configured.")
    rows = payload.get("veryUrgentCompanies")
    if not isinstance(rows, list) or not rows:
        raise ValueError("No urgent companies were supplied.")
    safe_rows = [row for row in rows[:25] if isinstance(row, dict)]
    lines = ["Very urgent SMA sales priorities", ""]
    for row in safe_rows:
        lines.append(
            f"- {str(row.get('companyName') or '-')[:200]} | PB {row.get('currentPb', '-')} | "
            f"Minimum {row.get('minPb', '-')} | {str(row.get('priority') or '-')[:80]}"
        )
    lines.extend(["", f"SMA page: {str(payload.get('pageUrl') or '')[:1000]}"])
    message = EmailMessage()
    message["Subject"] = f"SMA very urgent sales priorities ({len(safe_rows)})"
    message["From"] = settings.sales_notification_from
    message["To"] = settings.sales_notification_to
    message.set_content("\n".join(lines))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return len(safe_rows)

