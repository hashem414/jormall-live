"""Patient notification outbox and JOSMS delivery orchestration.

Appointment events first create an idempotent database record.  Sending is a
separate step, so an unavailable provider never rolls back an appointment
change.  HTTP success is recorded as submitted, not delivered; JorMall's
official response and delivery-report specifications are still required for a
true delivered state.
"""

from __future__ import annotations

import logging

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import get_conn
from .josms import (
    JOSMSConfigurationError,
    JOSMSProviderError,
    JOSMSTemporaryError,
    configuration_status,
    send_service_sms,
)
from .scheduling import next_available_slots
from .services import label as service_label

logger = logging.getLogger(__name__)

_AR_MONTHS = [
    "كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
    "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول",
]

_KINDS = {
    "appointment_requested",
    "appointment_confirmed",
    "appointment_rescheduled",
    "patient_cancelled",
    "clinic_cancelled",
}


def _fmt_ar(date_iso: str, time_str: str) -> str:
    _, month, day = (int(p) for p in date_iso.split("-"))
    hour, minute = (int(p) for p in time_str.split(":"))
    period = "ص" if hour < 12 else "م"
    return f"{day} {_AR_MONTHS[month - 1]} — {hour % 12 or 12}:{minute:02d} {period}"


def _fmt_en(date_iso: str, time_str: str) -> str:
    from datetime import date as Date

    year, month, day = (int(p) for p in date_iso.split("-"))
    hour, minute = (int(p) for p in time_str.split(":"))
    period = "AM" if hour < 12 else "PM"
    date_label = Date(year, month, day).strftime("%d %b")
    return f"{date_label} — {hour % 12 or 12}:{minute:02d} {period}"


def build_cancellation_notice(appointment: dict, slots: list[dict]) -> tuple[str, str]:
    """Detailed in-chat cancellation copy with nearby rebooking options."""
    settings = get_settings()
    when_ar = _fmt_ar(appointment["date"], appointment["time"])
    when_en = _fmt_en(appointment["date"], appointment["time"])
    service = appointment.get("service")
    svc_ar = f" ({service_label(service, 'ar')})" if service else ""
    svc_en = f" ({service_label(service, 'en')})" if service else ""

    if slots:
        options_ar = "\n".join(f"• {_fmt_ar(s['date'], s['time'])}" for s in slots)
        options_en = "\n".join(f"• {_fmt_en(s['date'], s['time'])}" for s in slots)
        tail_ar = f"\n\nهذه أقرب الأوقات المتاحة لإعادة الحجز:\n{options_ar}"
        tail_en = f"\n\nHere are the nearest available times to rebook:\n{options_en}"
    else:
        tail_ar = "\n\nتواصل معنا لاختيار موعد بديل."
        tail_en = "\n\nPlease contact us to arrange another time."

    body_ar = (
        f"عزيزنا {appointment['full_name']}، نعتذر — تم إلغاء موعدك{svc_ar} "
        f"بتاريخ {when_ar} من قِبل العيادة. يُرجى إعادة حجز موعد جديد."
        f"{tail_ar}\n\nللحجز: {settings.clinic_phone}"
    )
    body_en = (
        f"Dear {appointment['full_name']}, we are sorry — your appointment{svc_en} "
        f"on {when_en} has been cancelled by the clinic. Please rebook a new appointment."
        f"{tail_en}\n\nTo book: {settings.clinic_phone}"
    )
    return body_ar, body_en


def _appointment_row(appointment_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT a.id, a.full_name, a.phone, a.service, a.gender,
                   a.appointment_date, a.appointment_time, a.conversation_id,
                   c.lang
            FROM appointments a
            LEFT JOIN conversations c ON c.id = a.conversation_id
            WHERE a.id = %s
            """,
            (appointment_id,),
        ).fetchone()


def _message_copy(row: dict, kind: str, slots: list[dict]) -> tuple[str, str, str, str]:
    settings = get_settings()
    appointment = {
        "full_name": row["full_name"],
        "date": row["appointment_date"].isoformat(),
        "time": row["appointment_time"].strftime("%H:%M"),
        "service": row["service"],
    }
    when_ar = _fmt_ar(appointment["date"], appointment["time"])
    when_en = _fmt_en(appointment["date"], appointment["time"])

    if kind == "clinic_cancelled":
        body_ar, body_en = build_cancellation_notice(appointment, slots)
        sms_ar = f"كارماليت: نعتذر، ألغت العيادة موعدك بتاريخ {when_ar}. لإعادة الحجز: {settings.clinic_phone}"
        sms_en = f"Karmalite: We are sorry, the clinic cancelled your appointment on {when_en}. Rebook: {settings.clinic_phone}"
    elif kind == "appointment_confirmed":
        sms_ar = f"كارماليت: تم تأكيد موعدك بتاريخ {when_ar}. للاستفسار: {settings.clinic_phone}"
        sms_en = f"Karmalite: Your appointment on {when_en} is confirmed. Enquiries: {settings.clinic_phone}"
        body_ar, body_en = sms_ar, sms_en
    elif kind == "appointment_rescheduled":
        sms_ar = f"كارماليت: استلمنا طلب نقل موعدك إلى {when_ar}. الموعد غير مؤكد حتى تصلك رسالة تأكيد."
        sms_en = f"Karmalite: We received your request to move the appointment to {when_en}. It is not confirmed yet."
        body_ar, body_en = sms_ar, sms_en
    elif kind == "patient_cancelled":
        sms_ar = f"كارماليت: تم إلغاء موعدك بتاريخ {when_ar} بناءً على طلبك. للحجز من جديد: {settings.clinic_phone}"
        sms_en = f"Karmalite: Your appointment on {when_en} was cancelled as requested. Rebook: {settings.clinic_phone}"
        body_ar, body_en = sms_ar, sms_en
    else:  # appointment_requested
        sms_ar = f"كارماليت: استلمنا طلب موعدك بتاريخ {when_ar}. الطلب غير مؤكد حتى تصلك رسالة تأكيد."
        sms_en = f"Karmalite: We received your appointment request for {when_en}. It is not confirmed until you receive confirmation."
        body_ar, body_en = sms_ar, sms_en

    return body_ar, body_en, sms_ar, sms_en


def create_appointment_notification(
    appointment_id: int,
    kind: str,
    *,
    lang: str | None = None,
) -> dict | None:
    """Create one idempotent outbox row per appointment event."""
    if kind not in _KINDS:
        raise ValueError(f"Unknown appointment notification kind: {kind}")
    row = _appointment_row(appointment_id)
    if row is None:
        return None

    language = lang if lang in {"ar", "en"} else (row["lang"] or "ar")
    slots = next_available_slots(row["gender"] or "unknown", limit=5) if kind == "clinic_cancelled" else []
    body_ar, body_en, sms_ar, sms_en = _message_copy(row, kind, slots)

    with get_conn() as conn, conn.transaction():
        notice = conn.execute(
            """
            INSERT INTO notifications
                (appointment_id, phone, kind, language, body_ar, body_en,
                 sms_body_ar, sms_body_en, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (appointment_id, kind) WHERE appointment_id IS NOT NULL DO NOTHING
            RETURNING id, status
            """,
            (
                row["id"], row["phone"], kind, language, body_ar, body_en,
                sms_ar, sms_en, Jsonb({"slots": slots}),
            ),
        ).fetchone()
        created = notice is not None
        if notice is None:
            notice = conn.execute(
                "SELECT id, status FROM notifications WHERE appointment_id = %s AND kind = %s",
                (row["id"], kind),
            ).fetchone()

        if created and row["conversation_id"]:
            chat_body = body_en if language == "en" else body_ar
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, metadata)
                VALUES (%s, 'assistant', %s, %s)
                """,
                (row["conversation_id"], chat_body, Jsonb({"kind": kind})),
            )

    logger.info("notification #%s kind=%s created=%s", notice["id"], kind, created)
    return {
        "notification_id": notice["id"],
        "phone": row["phone"],
        "slots": slots,
        "created": created,
        "status": notice["status"],
        "delivered_to_chat": bool(created and row["conversation_id"]),
        "body_ar": body_ar,
        "body_en": body_en,
    }


def notify_clinic_cancellation(appointment_id: int) -> dict | None:
    return create_appointment_notification(appointment_id, "clinic_cancelled")


def list_notifications(status: str | None = "pending", limit: int = 50) -> list[dict]:
    query = """
        SELECT n.id, n.phone, n.kind, n.language, n.status, n.attempts,
               n.response_verified, n.last_error, n.next_attempt_at,
               n.submitted_at, n.delivered_at, n.created_at,
               a.full_name, a.appointment_date, a.appointment_time
        FROM notifications n
        LEFT JOIN appointments a ON a.id = n.appointment_id
        {where}
        ORDER BY n.created_at DESC
        LIMIT %s
    """.format(where="WHERE n.status = %s" if status else "")
    params = (status, limit) if status else (limit,)
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def _claim_notification(notification_id: int | None = None) -> dict | None:
    settings = get_settings()
    with get_conn() as conn, conn.transaction():
        return conn.execute(
            """
            WITH candidate AS (
                SELECT id
                FROM notifications
                WHERE (%s IS NULL OR id = %s)
                  AND attempts < %s
                  AND (
                    status = 'pending'
                    OR (status = 'failed' AND next_attempt_at IS NOT NULL AND next_attempt_at <= now())
                    OR (status = 'processing' AND processing_started_at < now() - interval '10 minutes')
                  )
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE notifications n
            SET status = 'processing', attempts = attempts + 1,
                processing_started_at = now(), updated_at = now()
            FROM candidate
            WHERE n.id = candidate.id
            RETURNING n.id, n.phone, n.language, n.sms_body_ar, n.sms_body_en, n.attempts
            """,
            (notification_id, notification_id, settings.josms_max_attempts),
        ).fetchone()


def send_notification(notification_id: int | None = None) -> dict | None:
    """Claim and submit one queued notification. Safe to call concurrently."""
    state = configuration_status()
    if not state["enabled"] or not state["configured"]:
        return {"status": "disabled", **state}

    notice = _claim_notification(notification_id)
    if notice is None:
        return None

    message = notice["sms_body_en"] if notice["language"] == "en" else notice["sms_body_ar"]
    reference = f"NOTIF-{notice['id']}"
    settings = get_settings()

    try:
        result = send_service_sms(
            phone_number=notice["phone"],
            message=message,
            reference_id=reference,
        )
    except JOSMSConfigurationError as exc:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE notifications
                SET status = 'pending', attempts = GREATEST(attempts - 1, 0),
                    processing_started_at = NULL, last_error = %s, updated_at = now()
                WHERE id = %s
                """,
                (str(exc), notice["id"]),
            )
        return {"id": notice["id"], "status": "disabled", "error": str(exc)}
    except (JOSMSTemporaryError, JOSMSProviderError) as exc:
        temporary = isinstance(exc, JOSMSTemporaryError)
        can_retry = temporary and notice["attempts"] < settings.josms_max_attempts
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE notifications
                SET status = 'failed', processing_started_at = NULL, last_error = %s,
                    next_attempt_at = CASE WHEN %s THEN now() + make_interval(mins => %s) ELSE NULL END,
                    updated_at = now()
                WHERE id = %s
                """,
                (str(exc), can_retry, settings.josms_retry_minutes, notice["id"]),
            )
        logger.warning("notification #%s failed retry=%s: %s", notice["id"], can_retry, exc)
        return {
            "id": notice["id"], "status": "failed", "retry_scheduled": can_retry,
            "error": str(exc),
        }

    status = "submitted" if result.acceptance_verified else "submitted_unverified"
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE notifications
            SET status = %s, provider = 'josms', provider_reference = %s,
                provider_response = %s, response_verified = %s,
                processing_started_at = NULL, next_attempt_at = NULL,
                submitted_at = now(), sent_at = now(), last_error = NULL, updated_at = now()
            WHERE id = %s
            """,
            (
                status, result.reference_id, result.provider_response,
                result.acceptance_verified, notice["id"],
            ),
        )
    return {
        "id": notice["id"],
        "status": status,
        "response_verified": result.acceptance_verified,
    }


def send_pending_notifications(limit: int = 20) -> list[dict]:
    if limit < 1:
        return []
    results = []
    for _ in range(min(limit, 100)):
        result = send_notification()
        if result is None:
            break
        results.append(result)
        if result.get("status") == "disabled":
            break
    return results


def retry_notification(notification_id: int) -> bool:
    """Requeue only an unsent/failed record; submitted messages are not duplicated."""
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE notifications
            SET status = 'pending', next_attempt_at = now(), last_error = NULL,
                processing_started_at = NULL, updated_at = now()
            WHERE id = %s AND status IN ('pending','failed')
            RETURNING id
            """,
            (notification_id,),
        ).fetchone()
    return row is not None


def mark_notification_sent(notification_id: int) -> bool:
    """Legacy manual override; prefer JOSMS submission and provider reports."""
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE notifications
            SET status = 'sent', sent_at = now(), updated_at = now()
            WHERE id = %s RETURNING id
            """,
            (notification_id,),
        ).fetchone()
    return row is not None
