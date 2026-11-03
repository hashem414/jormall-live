"""
منطق المواعيد والخانات المتاحة.

مصدر القواعد هو دوام العيادة نفسه:
  • السبت–الخميس 09:00–19:00
  • الجمعة مغلق بالكامل

الموقع العام يذكر ساعات رجال حتى منتصف الليل، لكن نطاق الأيام والخدمات غير معتمد؛
لذلك لا نعرض أي خانة بعد الدوام العام إلى أن تؤكدها العيادة.

الخانة كل 30 دقيقة. الخانة المحجوزة (requested أو confirmed) بتختفي من المتاح،
وخانات اليوم الحالي بتختفي لو ما ضل عليها ساعة على الأقل.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, time, timedelta

from .config import get_settings
from .db import get_conn
from .doctors import assigned_doctor
from .text_utils import normalize_arabic

SLOT_MINUTES = 30
OPEN_MINUTE = 9 * 60           # 09:00
CLOSE_MINUTE = 19 * 60         # 19:00 للجميع
CLOSE_MINUTE_MEN = CLOSE_MINUTE  # لا ساعات إضافية قبل اعتماد نطاق دوام الرجال
FRIDAY = 4                     # weekday(): الاثنين = 0
MIN_LEAD_MINUTES = 60          # ما بنقبل حجز خلال أقل من ساعة
# الخانة اللي بنعرضها بالمحادثة لازم تضل قابلة للحجز لما يرد العميل بعد شوي.
# بدون هالهامش كان البوت يعرض «٤:٣٠» الساعة ٣:٢٥، وبعد رسالتين يرفضها لأنها
# دخلت نافذة الساعة — فالعميل بيشوف عرضاً ثم اعتذاراً عن نفس الوقت.
OFFER_LEAD_MINUTES = MIN_LEAD_MINUTES + 20
MAX_DAYS_AHEAD = 60
CANCELLATION_NOTICE_HOURS = 24  # سياسة العيادة: الإلغاء قبل 24 ساعة على الأقل


def _fmt(minute: int) -> str:
    """1140 → «٧ م» بصيغة عربية مقروءة."""
    hour, mins = divmod(minute % (24 * 60), 60)
    period = "ص" if hour < 12 else "م"
    display = hour % 12 or 12
    digits = str(display).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    return f"{digits}:{mins:02d} {period}" if mins else f"{digits} {period}"


def hours_summary() -> str:
    """
    ملخّص الدوام مُولَّد من الثوابت أعلاه، بينحقن بالبرومبت.
    السبب: كانت أوقات الدوام مكتوبة يدوياً بالبرومبت وبقاعدة المعرفة وبالكود —
    ثلاث نسخ بتفترق أول ما تتغير المواعيد. هلأ الكود والبرومبت مصدرهم واحد.
    """
    return (
        f"الدوام العام السبت–الخميس من {_fmt(OPEN_MINUTE)} حتى {_fmt(CLOSE_MINUTE)}. "
        "الجمعة مغلق. ساعات الرجال الممتدة المذكورة علناً تحتاج تأكيد الاستقبال ولا تظهر كنوبات حجز تلقائية."
    )


@dataclass
class DayAvailability:
    date: Date
    is_open: bool
    reason: str | None
    slots: list[str]

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "is_open": self.is_open,
            "reason": self.reason,
            "slots": self.slots,
        }


def _closing_minute(gender: str) -> int:
    return CLOSE_MINUTE_MEN if gender == "male" else CLOSE_MINUTE


def _all_slots(day: Date, gender: str) -> list[time]:
    """كل الخانات النظرية لهذا اليوم قبل خصم المحجوز."""
    if day.weekday() == FRIDAY:
        return []

    slots: list[time] = []
    for minute in range(OPEN_MINUTE, _closing_minute(gender), SLOT_MINUTES):
        slots.append(time(hour=(minute // 60) % 24, minute=minute % 60))
    return slots


def _booked_slots(
    day: Date, service: str | None = None, doctor_id: str | None = None
) -> set[time]:
    """
    الأوقات المحجوزة اللي بتمنع حجزاً جديداً.

    الخانة صارت بتستوعب أكثر من موعد بنفس الوقت ما دامت **الخدمة مختلفة**
    (خدمة = غرفة/جهاز). فالمانع هو وجود موعد بنفس الوقت **ولنفس الخدمة**.
    بدون تحديد خدمة ما بنقدر نحكم، فبنرجّع فاضي بدل ما نخفي أوقاتاً متاحة.
    """
    if service is None and doctor_id is None:
        return set()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT appointment_time
            FROM appointments
            WHERE appointment_date = %s
              AND (COALESCE(service, '') = %s OR doctor_id = %s)
              AND status IN ('requested', 'confirmed')
            """,
            (day, service or "", doctor_id or ""),
        ).fetchall()
    return {r["appointment_time"] for r in rows}


def person_slots(day: Date, phone: str | None, email: str | None = None) -> set[time]:
    """
    أوقات هذا الشخص نفسه بذاك اليوم — ما بيقدر يكون بغرفتين بنفس اللحظة،
    حتى لو الخدمتين مختلفتين.
    """
    if not phone and not email:
        return set()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT appointment_time
            FROM appointments
            WHERE appointment_date = %s
              AND status IN ('requested', 'confirmed')
              AND (phone = %s OR (email IS NOT NULL AND lower(email) = %s))
            """,
            (day, phone or "", (email or "").strip().lower()),
        ).fetchall()
    return {r["appointment_time"] for r in rows}


def get_availability(
    day: Date,
    gender: str = "unknown",
    now: datetime | None = None,
    *,
    lead_minutes: int = MIN_LEAD_MINUTES,
    service: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    doctor_id: str | None = None,
) -> DayAvailability:
    """
    `lead_minutes` بيسمح نعرض بتحفّظ ونقبل بسماحة: العرض بالمحادثة بيستخدم
    هامشاً أوسع (OFFER_LEAD_MINUTES) حتى ما تختفي الخانة وقت ما يرد العميل،
    بينما التحقق وقت الحجز بيضل على الحد الأصلي فما نرفض حجزاً صالحاً.

    `service` بيحدد شو محجوز فعلاً — الخانة بتستوعب خدمات مختلفة بنفس الوقت.
    `phone`/`email` بيشيلوا الأوقات اللي هذا الشخص محجوزها أصلاً.
    """
    now = now or datetime.now()
    today = now.date()

    if day < today:
        return DayAvailability(day, False, "past", [])
    if (day - today).days > MAX_DAYS_AHEAD:
        return DayAvailability(day, False, "too_far", [])
    if day.weekday() == FRIDAY:
        return DayAvailability(day, False, "friday_closed", [])

    doctor = assigned_doctor(service, doctor_id)
    booked = _booked_slots(day, service, doctor.id if doctor else None) | person_slots(day, phone, email)
    cutoff = now + timedelta(minutes=lead_minutes)

    available = [
        slot.strftime("%H:%M")
        for slot in _all_slots(day, gender)
        if slot not in booked
        and (day > today or datetime.combine(day, slot) >= cutoff)
    ]
    return DayAvailability(day, bool(available), None if available else "fully_booked", available)


def is_slot_available(
    day: Date,
    slot: time,
    gender: str = "unknown",
    now: datetime | None = None,
    *,
    service: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    doctor_id: str | None = None,
) -> bool:
    return slot.strftime("%H:%M") in get_availability(
        day, gender, now, service=service, phone=phone, email=email, doctor_id=doctor_id
    ).slots


def active_appointment_count(phone: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT count(*) AS n FROM appointments
            WHERE phone = %s AND status = ANY(%s) AND appointment_date >= CURRENT_DATE
            """,
            (phone, list(ACTIVE_STATUSES)),
        ).fetchone()
    return int(row["n"])


def bookings_last_hour(phone: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM appointments"
            " WHERE phone = %s AND created_at > now() - interval '1 hour'",
            (phone,),
        ).fetchone()
    return int(row["n"])


def create_appointment(
    *,
    full_name: str,
    phone: str,
    day: Date,
    slot: time,
    service: str | None = None,
    gender: str = "unknown",
    notes: str | None = None,
    conversation_id: int | None = None,
    lead_id: int | None = None,
    email: str | None = None,
    doctor_id: str | None = None,
    enforce_limits: bool = True,
) -> dict:
    """
    بيسجّل **طلب** موعد بحالة requested — مش موعد مؤكد.
    التأكيد النهائي بيتم من صفحة الأدمن بعد ما الاستقبال يتصل بالمريض.

    السقوف بتتطبّق هون مش بطبقة الأداة، عشان تشمل كل المسارات (شات + HTTP).
    الأدمن بيمرّر enforce_limits=False لما يضيف موعداً يدوياً.
    """
    settings = get_settings()

    if enforce_limits:
        active = active_appointment_count(phone)
        if active >= settings.max_active_appointments_per_phone:
            return {"ok": False, "error": "too_many_active", "active": active,
                    "limit": settings.max_active_appointments_per_phone}
        recent = bookings_last_hour(phone)
        if recent >= settings.max_bookings_per_hour_per_phone:
            return {"ok": False, "error": "rate_limited", "recent": recent,
                    "limit": settings.max_bookings_per_hour_per_phone}

    doctor = assigned_doctor(service, doctor_id)
    if doctor_id and doctor is None:
        return {"ok": False, "error": "doctor_not_eligible"}

    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO appointments (conversation_id, lead_id, full_name, phone, service,
                                      appointment_date, appointment_time, gender, notes, email,
                                      doctor_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id, appointment_date, appointment_time, status
            """,
            (conversation_id, lead_id, full_name, phone, service, day, slot,
             gender, notes, email, doctor.id if doctor else None),
        ).fetchone()

        if row is None:
            # ثلاثة فهارس فريدة ممكن تمنع الإدخال — بنميّز أيّهم عشان
            # الرسالة تكون مفيدة: «الخدمة محجوزة» غير «إنت أصلاً محجوز بهذا الوقت»
            clash = conn.execute(
                """
                SELECT (COALESCE(service, '') = %s)                             AS same_service,
                       (doctor_id = %s)                                          AS same_doctor,
                       (phone = %s OR (email IS NOT NULL AND lower(email) = %s)) AS same_person
                FROM appointments
                WHERE appointment_date = %s AND appointment_time = %s
                  AND status = ANY(%s)
                """,
                (service or "", doctor.id if doctor else "", phone, (email or "").strip().lower(),
                 day, slot, list(ACTIVE_STATUSES)),
            ).fetchall()

        if row is None:
            if any(c["same_person"] for c in clash):
                return {"ok": False, "error": "already_booked_this_slot"}
            if any(c["same_doctor"] for c in clash):
                return {"ok": False, "error": "doctor_taken"}
            return {"ok": False, "error": "service_taken"}

    return {
        "ok": True,
        "appointment_id": row["id"],
        "date": row["appointment_date"].isoformat(),
        "time": row["appointment_time"].strftime("%H:%M"),
        "status": row["status"],
        "doctor_id": doctor.id if doctor else None,
    }


# ======================================================================
# البحث والإلغاء — مسار حسّاس، كل خطوة فيه بتتحقق من الهوية
# ======================================================================
ACTIVE_STATUSES = ("requested", "confirmed")
_REFERENCE_PREFIX = "APT-"


def make_reference(appointment_id: int) -> str:
    """
    معرّف نصي للموعد بدل الرقم الخام.
    السبب: الموديل بيخلط بين رقم الموعد وترتيبه بالقائمة ويبعت 1 بدل 8 —
    وهاد بيعني محاولة إلغاء موعد شخص تاني. الصيغة النصية بتقطع هالالتباس.
    """
    return f"{_REFERENCE_PREFIX}{appointment_id}"


def parse_reference(reference: str) -> int | None:
    text = (reference or "").strip().upper()
    if not text.startswith(_REFERENCE_PREFIX):
        return None
    suffix = text[len(_REFERENCE_PREFIX):]
    return int(suffix) if suffix.isdigit() else None


def _name_tokens(name: str) -> set[str]:
    """توكنز مُطبّعة للمقارنة: «أحمد الخالدي» و «احمد خالدي» بيتطابقوا."""
    normalized = normalize_arabic((name or "").strip().lower())
    return {token for token in normalized.replace("-", " ").split() if len(token) >= 2}


def names_match(provided: str, stored: str) -> bool:
    """
    عامل تحقق ثانٍ بجانب رقم الهاتف.
    بنقبل تطابق جزئي (اسم أول فقط، أو ترتيب مختلف) بس لازم يكون في توكن مشترك —
    عشان رقم مكتوب غلط ما يفتح موعد شخص تاني.
    """
    a, b = _name_tokens(provided), _name_tokens(stored)
    return bool(a and b and a & b)


def find_appointments(phone: str, full_name: str, now: datetime | None = None) -> list[dict]:
    """
    مواعيد قادمة لرقم واسم مطابقين. الرقم لازم يكون مُطبّع مسبقاً (9627XXXXXXXX).
    بيرجّع الحد الأدنى من البيانات — ما في كشف معلومات مرضى تانيين.
    """
    now = now or datetime.now()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, full_name, service, doctor_id, gender, appointment_date, appointment_time, status
            FROM appointments
            WHERE phone = %s
              AND status = ANY(%s)
              AND appointment_date >= %s
            ORDER BY appointment_date, appointment_time
            """,
            (phone, list(ACTIVE_STATUSES), now.date()),
        ).fetchall()

    return [
        {
            "reference": make_reference(r["id"]),
            "date": r["appointment_date"].isoformat(),
            "time": r["appointment_time"].strftime("%H:%M"),
            "service": r["service"],
            "gender": r["gender"],
            "status": r["status"],
            "hours_until": round(
                (datetime.combine(r["appointment_date"], r["appointment_time"]) - now).total_seconds() / 3600,
                1,
            ),
        }
        for r in rows
        if names_match(full_name, r["full_name"])
    ]


def next_available_slots(
    gender: str = "unknown",
    *,
    limit: int = 6,
    days_ahead: int = 14,
    per_day: int = 2,
    now: datetime | None = None,
    lead_minutes: int = MIN_LEAD_MINUTES,
    service: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    doctor_id: str | None = None,
) -> list[dict]:
    """
    أقرب خانات متاحة عبر الأيام القادمة — تُعرض للعميل بعد الإلغاء ليحجز بديل بضغطة.
    بنوزّعها على أيام مختلفة (per_day) بدل ما نعطيه ٦ خانات بنفس الصباح.
    استعلام واحد لكل المدى بدل استعلام لكل يوم.
    """
    now = now or datetime.now()
    today = now.date()
    horizon = today + timedelta(days=days_ahead)

    # الخانة بتنحجز لخدمة بعينها، وبتنحجز كمان على الشخص نفسه مهما كانت الخدمة.
    # استعلام واحد بيجيب الاتنين بدل استعلامين على رابط بعيد.
    doctor = assigned_doctor(service, doctor_id)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT appointment_date, appointment_time,
                   (COALESCE(service, '') = %s)                       AS same_service,
                   (doctor_id = %s)                                  AS same_doctor,
                   (phone = %s OR (email IS NOT NULL AND lower(email) = %s)) AS same_person
            FROM appointments
            WHERE appointment_date BETWEEN %s AND %s AND status = ANY(%s)
            """,
            (
                service or "",                        # قيمة فارغة لا تطابق بيانات الحجز الصالحة
                doctor.id if doctor else "",
                phone or "",
                (email or "").strip().lower(),
                today, horizon, list(ACTIVE_STATUSES),
            ),
        ).fetchall()

    booked = {
        (r["appointment_date"], r["appointment_time"])
        for r in rows
        if (service is not None and r["same_service"]) or r["same_doctor"] or r["same_person"]
    }
    cutoff = now + timedelta(minutes=lead_minutes)

    found: list[dict] = []
    day = today
    while day <= horizon and len(found) < limit:
        if day.weekday() != FRIDAY:
            taken_today = 0
            for slot in _all_slots(day, gender):
                if taken_today >= per_day or len(found) >= limit:
                    break
                if (day, slot) in booked or datetime.combine(day, slot) < cutoff:
                    continue
                found.append({"date": day.isoformat(), "time": slot.strftime("%H:%M")})
                taken_today += 1
        day += timedelta(days=1)
    return found


def resolve_and_reschedule(
    *,
    full_name: str,
    phone_raw: str,
    reference: str | None,
    new_date: Date,
    new_time: time,
    notes: str | None = None,
    by: str = "self-service",
    now: datetime | None = None,
) -> dict:
    """
    نقل موعد لوقت جديد كعملية واحدة.

    الترتيب مقصود: بنحجز الجديد **قبل** ما نلغي القديم، والاثنين داخل ترانزاكشن وحدة.
    لو الخانة الجديدة انحجزت بين اللحظتين، الترانزاكشن بترجع والموعد القديم بيضل قائم —
    أسوأ حالة إن الزبون يضل على موعده الأصلي، مش إنه يفقده ويطلع بدون بديل.
    """
    from .text_utils import normalize_jordan_phone

    now = now or datetime.now()
    full_name = (full_name or "").strip()
    phone = normalize_jordan_phone((phone_raw or "").strip())

    if len(full_name) < 3:
        return {"ok": False, "error": "invalid_name"}
    if not phone:
        return {"ok": False, "error": "invalid_phone"}

    candidates = find_appointments(phone, full_name)
    if not candidates:
        return {"ok": False, "error": "no_appointments"}

    requested = parse_reference(reference or "")
    matched = next((c for c in candidates if parse_reference(c["reference"]) == requested), None)
    if matched is None:
        if len(candidates) != 1:
            return {"ok": False, "error": "ambiguous", "candidates": candidates}
        matched = candidates[0]

    old_id = parse_reference(matched["reference"])
    new_slot_text = new_time.strftime("%H:%M")

    with get_conn() as conn, conn.transaction():
        old = conn.execute(
            """
            SELECT id, full_name, phone, email, status, service, doctor_id, gender, notes,
                   conversation_id, lead_id, appointment_date, appointment_time
            FROM appointments WHERE id = %s FOR UPDATE
            """,
            (old_id,),
        ).fetchone()

        if old is None:
            return {"ok": False, "error": "not_found"}
        if old["phone"] != phone or not names_match(full_name, old["full_name"]):
            return {"ok": False, "error": "verification_failed"}
        if old["status"] not in ACTIVE_STATUSES:
            return {"ok": False, "error": "already_" + old["status"]}
        if old["appointment_date"] == new_date and old["appointment_time"] == new_time:
            return {"ok": False, "error": "same_slot"}

        # التحقق من التوفر بنفس قواعد الحجز العادي — بما فيها إن الخانة
        # بتنحجز لخدمة هذا الموعد تحديداً، مش لأي خدمة
        available = get_availability(
            new_date, old["gender"], now,
            service=old["service"] or "",
            phone=phone,
            email=old.get("email"),
            doctor_id=old.get("doctor_id"),
        ).slots
        if new_slot_text not in available:
            return {"ok": False, "error": "slot_taken"}

        created = conn.execute(
            """
            INSERT INTO appointments (conversation_id, lead_id, full_name, phone, service,
                                      appointment_date, appointment_time, gender, notes, email,
                                      doctor_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                old["conversation_id"], old["lead_id"], old["full_name"], phone, old["service"],
                new_date, new_time, old["gender"], notes if notes is not None else old["notes"],
                old["email"], old.get("doctor_id"),
            ),
        ).fetchone()

        if created is None:                      # حدا سبقنا للخانة بنفس اللحظة
            return {"ok": False, "error": "slot_taken"}

        # 'rescheduled' مش 'cancelled': الموعد ما انلغى، انتقل. الخلط بينهم
        # بيضخّم إحصائية الإلغاءات وبيخفي إن المريض ضل ملتزم بموعده.
        conn.execute(
            """
            UPDATE appointments
            SET status = 'rescheduled', cancelled_at = now(), cancelled_by = %s,
                cancel_reason = %s, updated_at = now()
            WHERE id = %s
            """,
            (by, f"نُقل إلى {new_date} {new_slot_text}", old_id),
        )

    return {
        "ok": True,
        "reference": make_reference(created["id"]),
        "previous_reference": matched["reference"],
        "previous_date": old["appointment_date"].isoformat(),
        "previous_time": old["appointment_time"].strftime("%H:%M"),
        "date": new_date.isoformat(),
        "time": new_slot_text,
        "service": old["service"],
        "doctor_id": old.get("doctor_id"),
        "status": "requested",
    }


def resolve_and_cancel(
    *,
    full_name: str,
    phone_raw: str,
    reference: str | None,
    reason: str | None = None,
    by: str = "chat",
) -> dict:
    """
    المسار الآمن الوحيد للإلغاء — يستخدمه الشات وواجهة «مواعيدي» معاً.

    الحدّ الأمني هو (الاسم + الرقم). المعرّف بينحلّ **داخل مواعيد صاحب الرقم فقط**،
    فحتى لو انبعت معرّف غلط ما بيقدر يلمس موعد شخص تاني.
    بيرجّع رموز أخطاء، وكل طبقة بتترجمها لرسالتها (نص للموديل، أو HTTP للواجهة).
    """
    from .text_utils import normalize_jordan_phone

    full_name = (full_name or "").strip()
    phone = normalize_jordan_phone((phone_raw or "").strip())

    if len(full_name) < 3:
        return {"ok": False, "error": "invalid_name"}
    if not phone:
        return {"ok": False, "error": "invalid_phone"}

    candidates = find_appointments(phone, full_name)
    if not candidates:
        return {"ok": False, "error": "no_appointments"}

    requested = parse_reference(reference or "")
    matched = next((c for c in candidates if parse_reference(c["reference"]) == requested), None)

    if matched is None:
        if len(candidates) == 1:
            matched = candidates[0]      # معرّف غلط + موعد وحيد = خطأ نسخ، مش خطر
        else:
            return {"ok": False, "error": "ambiguous", "candidates": candidates}

    result = cancel_appointment(
        parse_reference(matched["reference"]),
        phone,
        full_name=full_name,
        reason=reason,
        by=by,
    )
    if result["ok"]:
        result["service"] = matched.get("service")
    return result


def cancel_appointment(
    appointment_id: int,
    phone: str,
    *,
    full_name: str,
    reason: str | None = None,
    by: str = "chat",
    now: datetime | None = None,
) -> dict:
    """
    إلغاء موعد بعد إعادة التحقق من الرقم والاسم على نفس الصف.
    إعادة التحقق مقصودة: حتى لو الموديل مرّر رقم موعد غلط، ما بيقدر يلغي موعد شخص تاني.
    """
    now = now or datetime.now()

    with get_conn() as conn, conn.transaction():
        row = conn.execute(
            """
            SELECT id, full_name, phone, status, appointment_date, appointment_time
            FROM appointments WHERE id = %s FOR UPDATE
            """,
            (appointment_id,),
        ).fetchone()

        if row is None:
            return {"ok": False, "error": "not_found"}
        if row["phone"] != phone or not names_match(full_name, row["full_name"]):
            return {"ok": False, "error": "verification_failed"}
        if row["status"] not in ACTIVE_STATUSES:
            return {"ok": False, "error": "already_" + row["status"]}

        when = datetime.combine(row["appointment_date"], row["appointment_time"])
        if when < now:
            return {"ok": False, "error": "already_passed"}

        conn.execute(
            """
            UPDATE appointments
            SET status = 'cancelled', cancelled_at = now(), cancelled_by = %s,
                cancel_reason = %s, updated_at = now()
            WHERE id = %s
            """,
            (by, reason, appointment_id),
        )

    hours_until = round((when - now).total_seconds() / 3600, 1)
    return {
        "ok": True,
        "reference": make_reference(appointment_id),
        "date": row["appointment_date"].isoformat(),
        "time": row["appointment_time"].strftime("%H:%M"),
        "hours_until": hours_until,
        "late_cancellation": hours_until < CANCELLATION_NOTICE_HOURS,
    }
