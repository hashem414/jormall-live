"""
موقع العيادة.

مصدر البيانات هو `.env` وحده — ممنوع كتابة عنوان داخل البرومبت أو الكود،
لنفس السبب اللي منع كتابة الأسعار هناك: أي قيمة مكتوبة يدوياً بتتسرّب كحقيقة
وبتفضل مذكورة حتى بعد ما تتغير. عنوان غلط بيوصّل الزبون لمكان تاني.

لو الإعدادات فاضية، النظام **ما بيخترع عنوان** — بيحوّل العميل للاستقبال.
"""

from __future__ import annotations

from .config import get_settings


def is_configured() -> bool:
    s = get_settings()
    return bool(s.clinic_street and s.clinic_building)


def parts(lang: str = "ar") -> dict:
    s = get_settings()
    return {
        "area": s.clinic_area,
        "street": s.clinic_street,
        "building": s.clinic_building,
        "floor": s.clinic_floor,
        "landmark": s.clinic_landmark,
        "maps_url": s.clinic_maps_url,
        "address_en": s.clinic_address_en,
    }


def describe(lang: str = "ar") -> str:
    """وصف مقروء للعنوان: الشارع، المبنى، الطابق، وعلامة مميزة إن وُجدت."""
    s = get_settings()

    if lang == "en" and s.clinic_address_en:
        return s.clinic_address_en
    if lang == "ar" and s.clinic_address_ar:
        return s.clinic_address_ar

    segments: list[str] = []
    if s.clinic_area:
        segments.append(s.clinic_area)
    if s.clinic_street:
        segments.append(f"شارع {s.clinic_street}" if "شارع" not in s.clinic_street else s.clinic_street)
    if s.clinic_building:
        segments.append(
            s.clinic_building if any(w in s.clinic_building for w in ("مجمع", "عمارة", "مبنى", "برج"))
            else f"مبنى {s.clinic_building}"
        )
    if s.clinic_floor:
        segments.append(f"الطابق {s.clinic_floor}")
    if s.clinic_landmark:
        segments.append(f"({s.clinic_landmark})")

    return "، ".join(segments)
