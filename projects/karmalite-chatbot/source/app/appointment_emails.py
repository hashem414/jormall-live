"""Idempotent appointment lifecycle emails and treatment-care guidance."""

from __future__ import annotations

import logging
from datetime import date, time

from .db import get_conn
from .doctors import get_doctor
from .mailer import is_configured, is_valid_email, send_email
from .services import label as service_label

logger = logging.getLogger(__name__)

_STATUS_KINDS = {
    "confirmed": ("appointment_confirmed", "pre_treatment_care"),
    "completed": ("appointment_completed", "post_treatment_care"),
    "no_show": ("appointment_no_show",),
}

_AR_PRE_GENERAL = "اتبع تعليمات العيادة، وأخبر الطبيب عن الأمراض والحساسية وجميع الأدوية والمكملات قبل العلاج."
_AR_POST_GENERAL = "اتبع تعليمات الطبيب بعد العلاج وتواصل مع العيادة عند أي أعراض غير متوقعة أو متزايدة."


def _care(en: str, ar: str | None = None, *, post: bool = False) -> tuple[str, str]:
    return en, ar or (_AR_POST_GENERAL if post else _AR_PRE_GENERAL)


_PRE_CARE = {
    "botox_full_face": _care(
        "If your prescriber confirms it is safe, avoid aspirin, ibuprofen, naproxen, fish oil, vitamin E, and Ginkgo biloba for 7 days. Avoid alcohol for 24-48 hours and arrive with a clean, makeup-free face."
    ),
    "fillers": _care(
        "If your prescriber confirms it is safe, avoid aspirin, ibuprofen, naproxen, fish oil, vitamin E, and Ginkgo biloba for 7 days. Avoid alcohol for 24-48 hours and arrive with a clean, makeup-free face."
    ),
    "profhilo": _care(
        "If your prescriber confirms it is safe, avoid blood-thinning medicines and supplements. Avoid alcohol for 24-48 hours to reduce bruising risk."
    ),
    "skin_boosters": _care(
        "If your prescriber confirms it is safe, avoid blood-thinning medicines and supplements. Avoid alcohol for 24-48 hours to reduce bruising risk."
    ),
    **{
        service: _care(
            "Shave the area 12-24 hours before treatment. Avoid direct sun and tanning beds for 2-4 weeks; do not wax, pluck, or thread for at least 4 weeks. Pause retinols and AHAs on the area for 3-5 days."
        )
        for service in ("laser_full_body_women", "laser_full_body_men", "laser_single_area")
    },
    "laser_tattoo_removal": _care(
        "Avoid sun, tanning, and self-tanners for 4 weeks. Shave densely hairy areas and arrive with clean skin free of lotions."
    ),
    "hydrafacial": _care(
        "Pause retinoids and chemical exfoliants for 3-5 days, avoid unprotected sun exposure, and arrive with a clean face."
    ),
    "dermapen": _care(
        "Pause retinoids and chemical exfoliants for 3-5 days, avoid unprotected sun exposure, and arrive with a clean face."
    ),
    "microneedling_rf": _care(
        "Stop retinoids and exfoliating acids for 5-7 days and strictly avoid sun for 2-4 weeks. Tell the clinician about any history of cold sores; preventive antiviral treatment may need medical review."
    ),
    "fractional_co2": _care(
        "Stop retinoids and exfoliating acids for 5-7 days and strictly avoid sun for 2-4 weeks. Tell the clinician about any history of cold sores; preventive antiviral treatment may need medical review."
    ),
    "chemical_peel": _care(
        "Stop retinols, AHAs/BHAs, and physical exfoliants for 5-7 days and avoid sun exposure."
    ),
    "hifu": _care("Make sure the treatment area has no active infection or open wound."),
    "prp_face": _care(
        "Hydrate well the day before. If your prescriber confirms it is safe, avoid NSAIDs such as ibuprofen and aspirin for 7 days."
    ),
    "prp": _care(
        "Hydrate well the day before. If your prescriber confirms it is safe, avoid NSAIDs such as ibuprofen and aspirin for 7 days."
    ),
    "hair_mesotherapy": _care(
        "Hydrate well the day before. If your prescriber confirms it is safe, avoid NSAIDs such as ibuprofen and aspirin for 7 days."
    ),
    "endermolift": _care("Arrive with clean, makeup-free skin and stay well hydrated."),
    "ultratone_face": _care("Arrive with clean, makeup-free skin and stay well hydrated."),
    **{
        service: _care(
            "Hydrate well in the days before treatment. Keep the area clean and free of thick lotions or oils. Avoid a heavy meal immediately before Emsculpt or UltraTone."
        )
        for service in ("lpg_body", "cryolipolysis", "fat_freezing_360", "exilis", "emsculpt", "ultratone_body")
    },
    "carboxy_therapy": _care("Wear loose, comfortable clothing."),
    "body_peel": _care("Wear loose clothing and avoid sun exposure on the area to be peeled."),
    "spray_tan": _care(
        "Exfoliate and shave 24 hours before. On the appointment day, do not apply body lotion, deodorant, perfume, or makeup."
    ),
    "solarium": _care(
        "Exfoliate and shave 24 hours before. On the appointment day, do not apply body lotion, deodorant, perfume, or makeup."
    ),
    **{
        service: _care(
            "Bring your complete medical history, current medication list, relevant lab results or imaging, and a list of questions or aesthetic goals. Shower normally before intimate-wellness or gynecology examinations."
        )
        for service in (
            "gynecology_consultation", "pregnancy_postpartum", "intimate_wellness",
            "aesthetic_gynecology", "plastic_surgery_consultation",
            "aesthetic_surgery_consultation", "dermatology_consultation", "consultation", "not_sure",
        )
    },
}

_POST_CARE = {
    "botox_full_face": _care(
        "Do not rub or massage the area. Stay upright for at least 4 hours. Avoid strenuous exercise, saunas, tanning beds, other hot environments, and alcohol for 24 hours.", post=True
    ),
    "fillers": _care(
        "Do not rub or massage the area unless instructed. Avoid strenuous exercise, saunas, tanning beds, other hot environments, and alcohol for 24 hours.", post=True
    ),
    "profhilo": _care(
        "Do not touch injection sites or apply makeup for at least 12 hours. Avoid strenuous exercise and extreme hot or cold temperatures for 24 hours.", post=True
    ),
    "skin_boosters": _care(
        "Do not touch injection sites or apply makeup for at least 12 hours. Avoid strenuous exercise and extreme hot or cold temperatures for 24 hours.", post=True
    ),
    **{
        service: _care(
            "Avoid sun and apply SPF 50+ consistently. Avoid hot showers, saunas, swimming pools, and tight clothing for 24-48 hours. Use a soothing product such as aloe vera if the clinic approves it.", post=True
        )
        for service in ("laser_full_body_women", "laser_full_body_men", "laser_single_area")
    },
    "laser_tattoo_removal": _care(
        "Keep the area clean and dry. Apply only clinician-prescribed antibiotic or healing ointment and cover it as directed. Do not pick blisters or scabs, and avoid swimming or soaking until healed.", post=True
    ),
    "hydrafacial": _care(
        "Avoid washing your face or applying makeup for the first few hours. Pause active skincare ingredients for 48 hours.", post=True
    ),
    "dermapen": _care(
        "Do not touch your face for at least 4 hours. Use only gentle cleanser and pure hyaluronic acid if approved. Avoid makeup and sweating for 24 hours and direct sun for one week.", post=True
    ),
    "microneedling_rf": _care(
        "Redness, swelling, and downtime are expected. Apply only prescribed healing ointments; do not pick, peel, or scratch. Strictly avoid sun and use physical SPF only after the skin has closed, usually after 48 hours.", post=True
    ),
    "fractional_co2": _care(
        "Redness, swelling, and downtime are expected. Apply only prescribed healing ointments; do not pick, peel, or scratch. Strictly avoid sun and use physical SPF only after the skin has closed, usually after 48 hours.", post=True
    ),
    "chemical_peel": _care(
        "Use strict sun protection, do not pull or pick peeling skin, and keep the skin well moisturized with gentle products.", post=True
    ),
    "hifu": _care(
        "Avoid hot facial water, saunas, and intense workouts for 24-48 hours. Mild redness or swelling can occur and should settle quickly.", post=True
    ),
    **{
        service: _care(
            "Do not wash the treated face or scalp for 12-24 hours. Avoid NSAIDs afterward only for the period your clinician and prescriber approve.", post=True
        )
        for service in ("prp_face", "prp", "hair_mesotherapy")
    },
    "endermolift": _care("Stay well hydrated and maintain the skincare routine recommended by the clinic.", post=True),
    "ultratone_face": _care("Stay well hydrated and maintain the skincare routine recommended by the clinic.", post=True),
    **{
        service: _care(
            "Stay well hydrated unless you have a medical fluid restriction, and use light activity such as walking if approved. Avoid extreme localized heat after fat-freezing treatments.", post=True
        )
        for service in ("lpg_body", "cryolipolysis", "fat_freezing_360", "exilis", "emsculpt", "ultratone_body")
    },
    "carboxy_therapy": _care(
        "Avoid bathing, swimming, or wetting the area for at least 4 hours. Mild injection-site bruising can occur.", post=True
    ),
    "body_peel": _care(
        "Keep skin well moisturized, do not pick flaking skin, avoid sun, and wear loose clothing to prevent friction.", post=True
    ),
    "spray_tan": _care(
        "Wear dark, loose clothing. Avoid showering, sweating, or getting wet for 8-12 hours, then moisturize daily to prolong the tan.", post=True
    ),
    "solarium": _care("Follow the clinic's service-specific aftercare and skin-protection instructions.", post=True),
    **{
        service: _care(
            "Follow the specialist's diagnostic, lifestyle, or pre-surgical instructions. Arrange recommended blood tests, imaging, or follow-up appointments before treatment.", post=True
        )
        for service in (
            "gynecology_consultation", "pregnancy_postpartum", "intimate_wellness",
            "aesthetic_gynecology", "plastic_surgery_consultation",
            "aesthetic_surgery_consultation", "dermatology_consultation", "consultation", "not_sure",
        )
    },
}


def email_event_kinds_for_status(status: str) -> tuple[str, ...]:
    return _STATUS_KINDS.get(status, ())


def _when(day: date, slot: time) -> str:
    return f"{day.isoformat()} at {slot.strftime('%H:%M')}"


def build_appointment_email(appointment: dict, kind: str) -> tuple[str, str]:
    """Build a bilingual plain-text email for one lifecycle event."""
    name = appointment["full_name"]
    service_id = appointment.get("service")
    service_en = service_label(service_id, "en") or "your treatment"
    service_ar = service_label(service_id, "ar") or "العلاج"
    when = _when(appointment["appointment_date"], appointment["appointment_time"])
    doctor = get_doctor(appointment.get("doctor_id"))
    doctor_line = f"\nDoctor: {doctor.name}" if doctor else ""
    header = f"Dear {name},\n\n"

    if kind == "appointment_confirmed":
        subject = "Appointment confirmed | تم تأكيد موعدك"
        body = (
            f"Your {service_en} appointment is confirmed for {when}.\n"
            f"تم تأكيد موعد {service_ar} بتاريخ {when}." + doctor_line
        )
    elif kind == "appointment_completed":
        subject = "Appointment completed | تم إكمال موعدك"
        body = (
            f"Your {service_en} appointment on {when} has been marked complete.\n"
            f"تم تسجيل موعد {service_ar} بتاريخ {when} كمكتمل."
        )
    elif kind == "appointment_no_show":
        subject = "We missed you | لم تحضر موعدك"
        body = (
            f"You were marked as not attending your {service_en} appointment on {when}. "
            "Please contact the clinic if this is incorrect or to arrange another appointment.\n"
            f"تم تسجيل عدم حضورك لموعد {service_ar} بتاريخ {when}. "
            "يرجى التواصل مع العيادة إذا كان ذلك غير صحيح أو لترتيب موعد آخر."
        )
    elif kind == "pre_treatment_care":
        subject = "Before your treatment | إرشادات قبل العلاج"
        en, ar = _PRE_CARE.get(service_id, (
            "Tell your clinician about medical conditions, allergies, medicines, supplements, pregnancy or breastfeeding, and recent procedures.",
            "أخبر الطبيب عن الحالات الصحية والحساسية والأدوية والمكملات والحمل أو الرضاعة والإجراءات الحديثة.",
        ))
        body = f"Before your {service_en} appointment:\n{en}\n\nقبل موعد {service_ar}:\n{ar}"
    elif kind == "post_treatment_care":
        subject = "After your treatment | إرشادات بعد العلاج"
        en, ar = _POST_CARE.get(service_id, (
            "Follow the written instructions from your treating clinician. Do not rub, pick, or apply products to the treated area unless instructed.",
            "اتبع تعليمات الطبيب المعالج المكتوبة، ولا تفرك أو تعبث أو تضع منتجات على المنطقة المعالجة إلا حسب التعليمات.",
        ))
        body = f"After your {service_en} treatment:\n{en}\n\nبعد علاج {service_ar}:\n{ar}"
    else:
        raise ValueError(f"Unknown appointment email kind: {kind}")

    safety = (
        "\n\nDo not stop prescribed medicine unless your prescriber tells you to. "
        "Your treating clinician's instructions take priority. Seek urgent medical help for difficulty breathing, swallowing or speaking, major vision changes, rapidly worsening pain or swelling, or a severe allergic reaction."
        "\n\nلا توقف دواءً موصوفاً إلا بتوجيه الطبيب. تعليمات الطبيب المعالج لها الأولوية. "
        "اطلب مساعدة طبية عاجلة عند صعوبة التنفس أو البلع أو الكلام، أو تغير كبير بالرؤية، أو ألم أو تورم متزايد بسرعة، أو تحسس شديد."
    )
    return subject, header + body + safety


def queue_status_emails(appointment_id: int, status: str) -> list[dict]:
    """Create each email event once and return only newly queued records."""
    kinds = email_event_kinds_for_status(status)
    if not kinds:
        return []

    with get_conn() as conn:
        appointment = conn.execute(
            """
            SELECT id, full_name, email, service, doctor_id, appointment_date, appointment_time
            FROM appointments WHERE id = %s
            """,
            (appointment_id,),
        ).fetchone()
        if not appointment or not is_valid_email(appointment.get("email") or ""):
            return []

        queued = []
        for kind in kinds:
            subject, text_body = build_appointment_email(appointment, kind)
            row = conn.execute(
                """
                INSERT INTO appointment_email_events
                    (appointment_id, kind, recipient, subject, text_body)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (appointment_id, kind) DO NOTHING
                RETURNING id, kind, status
                """,
                (appointment_id, kind, appointment["email"], subject, text_body),
            ).fetchone()
            if row:
                queued.append(row)
    return queued


def send_appointment_email(event_id: int) -> dict:
    """Send one queued event and retain the result for auditing/retry."""
    with get_conn() as conn:
        event = conn.execute(
            """
            UPDATE appointment_email_events
            SET status = 'sending', attempts = attempts + 1, updated_at = now()
            WHERE id = %s AND status IN ('pending', 'failed')
            RETURNING id, recipient, subject, text_body
            """,
            (event_id,),
        ).fetchone()
    if not event:
        return {"ok": False, "error": "not_pending"}

    try:
        if not is_configured():
            raise RuntimeError("SMTP is not configured")
        send_email(event["recipient"], event["subject"], event["text_body"])
    except Exception as exc:
        logger.exception("appointment email #%s failed", event_id)
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE appointment_email_events
                SET status = 'failed', last_error = %s, updated_at = now()
                WHERE id = %s
                """,
                (str(exc)[:1000], event_id),
            )
        return {"ok": False, "error": str(exc)}

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE appointment_email_events
            SET status = 'sent', sent_at = now(), last_error = NULL, updated_at = now()
            WHERE id = %s
            """,
            (event_id,),
        )
    return {"ok": True, "event_id": event_id}
