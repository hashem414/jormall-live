"""ذاكرة المحادثة: جلسات + رسائل مخزّنة بـ PostgreSQL (مش بالرام)."""

from __future__ import annotations

from datetime import date as Date
from datetime import time as Time

from psycopg.types.json import Jsonb

from .db import get_conn


def get_or_create_conversation(session_id: str, channel: str = "web", lang: str | None = None) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO conversations (session_id, channel, lang)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE
                SET updated_at = now(),
                    lang = COALESCE(EXCLUDED.lang, conversations.lang)
            RETURNING id
            """,
            (session_id, channel, lang),
        ).fetchone()
    return row["id"]


def find_conversation(session_id: str) -> int | None:
    """بيرجّع رقم المحادثة بدون ما ينشئ وحدة جديدة (للقراءة فقط)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE session_id = %s", (session_id,)
        ).fetchone()
    return row["id"] if row else None


def add_message(
    conversation_id: int,
    role: str,
    content: str,
    *,
    retrieved_ids: list[int] | None = None,
    metadata: dict | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, retrieved_ids, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                conversation_id,
                role,
                content,
                retrieved_ids or [],
                Jsonb(metadata or {}),
            ),
        )


_HISTORY_SQL = """
    SELECT role, content FROM (
        SELECT role, content, created_at
        FROM messages
        WHERE conversation_id = %s AND role IN ('user','assistant')
        ORDER BY created_at DESC
        LIMIT %s
    ) recent
    ORDER BY created_at ASC
"""


def get_history(conversation_id: int, turns: int = 8) -> list[dict]:
    """آخر N رسالة (user/assistant فقط) بترتيب زمني تصاعدي."""
    with get_conn() as conn:
        rows = conn.execute(_HISTORY_SQL, (conversation_id, turns * 2)).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def conversation_has_recent_appointment(conversation_id: int, minutes: int = 60) -> bool:
    """
    هل انحجز فعلاً موعد بهذه المحادثة مؤخراً؟

    بنستخدمها للتحقق من صدق الرد: لو الرد بيقول «تم تسجيل طلبك» وما في صف
    بقاعدة البيانات، فالعميل رح يجي بيوم ما إله موعد فيه.
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM appointments
            WHERE conversation_id = %s
              AND created_at > now() - make_interval(mins => %s)
            LIMIT 1
            """,
            (conversation_id, minutes),
        ).fetchone()
    return row is not None


def open_conversation(
    session_id: str, *, channel: str = "web", lang: str | None = None, turns: int = 8
) -> tuple[int, list[dict]]:
    """
    بداية كل رسالة: رقم المحادثة + سجلّها — باتصال واحد بدل اتنين.

    كانوا استدعاءين منفصلين، وكل واحد بياخد اتصال من الـ pool ويعمل COMMIT
    لحاله. على قاعدة بعيدة كل حجز اتصال بيكلّف رحلات، فدمجهم بيوفّر نص
    الرحلات بهاي المرحلة بدون أي تغيير بالسلوك.
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO conversations (session_id, channel, lang)
            VALUES (%s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE
                SET updated_at = now(),
                    lang = COALESCE(EXCLUDED.lang, conversations.lang)
            RETURNING id
            """,
            (session_id, channel, lang),
        ).fetchone()
        conversation_id = row["id"]
        rows = conn.execute(_HISTORY_SQL, (conversation_id, turns * 2)).fetchall()

    return conversation_id, [{"role": r["role"], "content": r["content"]} for r in rows]


def format_history(history: list[dict], limit: int = 6) -> str:
    if not history:
        return "(لا يوجد سجل سابق)"
    label = {"user": "العميل", "assistant": "المساعد"}
    return "\n".join(f"{label.get(m['role'], m['role'])}: {m['content']}" for m in history[-limit:])


def list_leads(status: str | None = None, limit: int = 50) -> list[dict]:
    query = """
        SELECT l.id, l.full_name, l.phone, l.service_interest, l.preferred_time,
               l.gender, l.notes, l.status, l.created_at, c.session_id, c.channel
        FROM leads l
        LEFT JOIN conversations c ON c.id = l.conversation_id
        {where}
        ORDER BY l.created_at DESC
        LIMIT %s
    """.format(where="WHERE l.status = %s" if status else "")
    params = (status, limit) if status else (limit,)
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def list_appointments(
    status: str | None = None,
    limit: int = 200,
    *,
    date_from: Date | None = None,
    date_to: Date | None = None,
    time_from: Time | None = None,
    time_to: Time | None = None,
) -> list[dict]:
    """
    مواعيد اللوحة مع فلترة اختيارية بمدى التاريخ والوقت.

    كل حدّ مستقل عن الباقي: لو انبعت طرف واحد بس (من بدون إلى، أو العكس)
    بينطبق لحاله كمدى مفتوح. الفلترة بالـ SQL مش بالواجهة عشان الـ LIMIT
    ينطبق **بعد** التصفية — لو صفّينا بالمتصفح رح نفلتر ٢٠٠ صف مقصوصين أصلاً
    وبتضيع مواعيد مطابقة برّا القص.
    """
    conditions: list[str] = []
    params: list = []

    if status:
        conditions.append("a.status = %s")
        params.append(status)
    if date_from is not None:
        conditions.append("a.appointment_date >= %s")
        params.append(date_from)
    if date_to is not None:
        conditions.append("a.appointment_date <= %s")
        params.append(date_to)
    if time_from is not None:
        conditions.append("a.appointment_time >= %s")
        params.append(time_from)
    if time_to is not None:
        conditions.append("a.appointment_time <= %s")
        params.append(time_to)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT a.id, a.full_name, a.phone, a.email, a.service, a.doctor_id,
               a.appointment_date, a.appointment_time,
               a.gender, a.notes, a.status, a.created_at,
               a.cancelled_by, a.cancelled_at, a.cancel_reason,
               c.session_id, c.channel
        FROM appointments a
        LEFT JOIN conversations c ON c.id = a.conversation_id
        {where}
        ORDER BY a.appointment_date ASC, a.appointment_time ASC
        LIMIT %s
    """
    params.append(limit)
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def get_appointment(appointment_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, full_name, phone, email, service, doctor_id,
                   appointment_date, appointment_time, gender, notes, status
            FROM appointments WHERE id = %s
            """,
            (appointment_id,),
        ).fetchone()


def update_appointment_status(appointment_id: int, status: str, *, by: str = "admin") -> str:
    """
    تحديث الحالة من لوحة التحكم.
    بنسجّل `cancelled_by` عند الإلغاء عشان نميّز إلغاء العيادة عن إلغاء المريض —
    الفرق مهم إدارياً وبيغيّر شو بنبعت للمريض.
    """
    with get_conn() as conn:
        if status in {"completed", "no_show"}:
            row = conn.execute(
                """
                UPDATE appointments
                SET status = %s, updated_at = now()
                WHERE id = %s
                  AND appointment_date + appointment_time
                      <= (now() AT TIME ZONE 'Asia/Amman')
                RETURNING id
                """,
                (status, appointment_id),
            ).fetchone()
            if row is None:
                exists = conn.execute(
                    "SELECT 1 FROM appointments WHERE id = %s", (appointment_id,)
                ).fetchone()
                return "too_early" if exists else "not_found"
        elif status == "cancelled":
            row = conn.execute(
                """
                UPDATE appointments
                SET status = 'cancelled', cancelled_at = now(), cancelled_by = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (by, appointment_id),
            ).fetchone()
        else:
            row = conn.execute(
                "UPDATE appointments SET status = %s, updated_at = now() WHERE id = %s RETURNING id",
                (status, appointment_id),
            ).fetchone()
    return "updated" if row is not None else "not_found"


def update_appointment_details(appointment_id: int, **fields) -> bool:
    """تحديث تفاصيل الموعد (الاسم، الهاتف، الإيميل، التاريخ، الوقت، الخدمة، الجنس، الملاحظات)."""
    allowed = {"full_name", "phone", "email", "appointment_date", "appointment_time",
               "service", "doctor_id", "gender", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [appointment_id]
    with get_conn() as conn:
        row = conn.execute(
            f"UPDATE appointments SET {set_clause}, updated_at = now() WHERE id = %s RETURNING id",
            values,
        ).fetchone()
    return row is not None


def update_lead_status(lead_id: int, status: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "UPDATE leads SET status = %s WHERE id = %s RETURNING id", (status, lead_id)
        ).fetchone()
    return row is not None


def set_escalation_handled(escalation_id: int, handled: bool = True) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "UPDATE escalations SET handled = %s WHERE id = %s RETURNING id",
            (handled, escalation_id),
        ).fetchone()
    return row is not None


def dashboard_stats() -> dict:
    """أرقام سريعة لأعلى صفحة الأدمن."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
              (SELECT count(*) FROM appointments WHERE status = 'requested')            AS pending_appointments,
              (SELECT count(*) FROM appointments
                 WHERE status = 'confirmed' AND appointment_date = CURRENT_DATE)        AS today_confirmed,
              (SELECT count(*) FROM appointments
                 WHERE appointment_date >= CURRENT_DATE
                   AND status IN ('requested','confirmed'))                             AS upcoming,
              (SELECT count(*) FROM leads WHERE status = 'new')                         AS new_leads,
              (SELECT count(*) FROM leads)                                              AS total_leads,
              (SELECT count(*) FROM escalations WHERE handled = false)                  AS open_escalations,
              (SELECT count(*) FROM escalations
                 WHERE handled = false AND level = 'emergency')                         AS emergencies,
              (SELECT count(*) FROM conversations)                                      AS conversations
            """
        ).fetchone()


def list_escalations(handled: bool = False, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT e.id, e.level, e.reason, e.handled, e.created_at,
                   e.full_name, e.phone, c.session_id
            FROM escalations e
            LEFT JOIN conversations c ON c.id = e.conversation_id
            WHERE e.handled = %s
            ORDER BY
                CASE e.level WHEN 'emergency' THEN 0 WHEN 'medical' THEN 1
                             WHEN 'manager' THEN 2 ELSE 3 END,
                e.created_at DESC
            LIMIT %s
            """,
            (handled, limit),
        ).fetchall()
