"""
تحقق البريد الإلكتروني قبل تثبيت الموعد.

ليش: قبل هيك كان أي حد يقدر يعبّي التقويم بأسماء وأرقام مخترعة. الرمز
بيثبت إن الإيميل موجود وإن اللي بيحجز واصل عليه.

القيود المقصودة:
  • الرمز بينخزّن **مهشّراً** (sha256) — تسريب قاعدة البيانات ما بيعطي رموزاً صالحة
  • محاولات إدخال محدودة — ٦ خانات = مليون احتمال، بس بدون حد المحاولات
    ممكن تنجرّب بالقوة الغاشمة
  • حدّ إرسال بالساعة لكل إيميل — حتى ما ينستخدم النظام لإغراق بريد شخص
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from .config import get_settings
from .db import get_conn
from .mailer import is_configured, normalize_email, send_verification_code

logger = logging.getLogger(__name__)

CODE_LENGTH = 6


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _new_code() -> str:
    """رمز عشوائي آمن تشفيرياً — `secrets` مش `random`."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def verification_required() -> bool:
    """التحقق شغّال فقط لما SMTP يكون مهيأ — عيادة شغّالة ما بتنكسر بدونه."""
    return is_configured()


def codes_sent_last_hour(email: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT count(*) AS n FROM email_verifications
            WHERE lower(email) = %s AND created_at > now() - interval '1 hour'
            """,
            (normalize_email(email),),
        ).fetchone()
    return int(row["n"])


def issue_code(conversation_id: int | None, email: str, lang: str = "ar") -> dict:
    """
    بينشئ رمزاً وبيبعته. بيرجّع dict فيها ok/error بدل ما ترمي —
    الطبقة اللي فوقها أداة بتحكي مع الموديل، فبتحتاج رسالة مفهومة.
    """
    settings = get_settings()
    email = normalize_email(email)

    if not verification_required():
        return {"ok": False, "error": "smtp_not_configured"}

    sent = codes_sent_last_hour(email)
    if sent >= settings.email_codes_per_hour:
        logger.warning("تجاوز حدّ إرسال رموز التحقق: %s (%d بالساعة)", email, sent)
        return {"ok": False, "error": "rate_limited", "sent_last_hour": sent}

    code = _new_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.email_code_ttl_minutes)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO email_verifications (conversation_id, email, code_hash, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (conversation_id, email, _hash(code), expires),
        )

    try:
        send_verification_code(email, code, lang)
    except Exception as exc:
        logger.exception("فشل إرسال رمز التحقق إلى %s", email)
        return {"ok": False, "error": "send_failed", "detail": str(exc)[:200]}

    return {"ok": True, "email": email, "ttl_minutes": settings.email_code_ttl_minutes}


def check_code(conversation_id: int | None, email: str, code: str) -> dict:
    """
    بيتحقق من آخر رمز غير منتهٍ لهذا (المحادثة + الإيميل).

    بنزوّد عدّاد المحاولات **قبل** المقارنة، حتى المحاولة الفاشلة تتحسب
    حتى لو انقطع الاتصال بعدها.
    """
    settings = get_settings()
    email = normalize_email(email)
    code = (code or "").strip()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, code_hash, attempts, verified_at, expires_at
            FROM email_verifications
            WHERE conversation_id IS NOT DISTINCT FROM %s AND lower(email) = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (conversation_id, email),
        ).fetchone()

        if row is None:
            return {"ok": False, "error": "no_code"}
        if row["verified_at"] is not None:
            return {"ok": True, "already_verified": True}
        if row["expires_at"] <= datetime.now(timezone.utc):
            return {"ok": False, "error": "expired"}
        if row["attempts"] >= settings.email_code_max_attempts:
            return {"ok": False, "error": "too_many_attempts"}

        conn.execute(
            "UPDATE email_verifications SET attempts = attempts + 1 WHERE id = %s",
            (row["id"],),
        )

        if not secrets.compare_digest(row["code_hash"], _hash(code)):
            remaining = settings.email_code_max_attempts - (row["attempts"] + 1)
            return {"ok": False, "error": "wrong_code", "attempts_left": max(0, remaining)}

        conn.execute(
            "UPDATE email_verifications SET verified_at = now() WHERE id = %s", (row["id"],)
        )

    logger.info("إيميل تحقّق بنجاح: %s", email)
    return {"ok": True, "email": email}


def is_verified(conversation_id: int | None, email: str) -> bool:
    """هل هذا الإيميل متحقّق منه بهذه المحادثة؟ بنستدعيها قبل كتابة الموعد."""
    if not verification_required():
        return True                      # SMTP مش مهيأ = التحقق معطّل

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM email_verifications
            WHERE conversation_id IS NOT DISTINCT FROM %s
              AND lower(email) = %s AND verified_at IS NOT NULL
            LIMIT 1
            """,
            (conversation_id, normalize_email(email)),
        ).fetchone()
    return row is not None
