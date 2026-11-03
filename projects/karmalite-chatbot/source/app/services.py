"""
كتالوج الخدمات — مصدر واحد للحقيقة.

بيتغذّى منه:
  • قيم enum لأداة `book_appointment` عشان الموديل ما يخترع خدمة مش موجودة
  • عرض اسم الخدمة وقائمة التعديل بلوحة التحكم (GET /services)

المصدر: القسم 4 من data/karmalite_kb.md — لما تتغير الخدمات هناك، عدّلها هون كمان.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    id: str
    ar: str
    en: str
    category_ar: str
    category_en: str
    duration_minutes: int | None = None
    gender: str | None = None   # None = للجميع، أو male / female

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ar": self.ar,
            "en": self.en,
            "category_ar": self.category_ar,
            "category_en": self.category_en,
            "duration_minutes": self.duration_minutes,
            "gender": self.gender,
        }


_INJECTABLES = ("الحقن التجميلية", "Injectables")
_LASER = ("الليزر", "Laser Treatments")
_SKIN = ("علاجات الوجه والبشرة", "Face & Skin Treatments")
_HAIR = ("علاجات الشعر", "Hair Treatments")
_BODY = ("نحت وتنسيق القوام", "Body Contouring")
_TANNING = ("التسمير", "Tanning")
_KARMAFEMME = ("KarmaFemme — صحة المرأة", "KarmaFemme — Women's Health")
_SURGERY = ("الجراحة التجميلية والترميمية", "Aesthetic & Reconstructive Surgery")
_OTHER = ("أخرى", "Other")

SERVICES: tuple[Service, ...] = (
    # No duration is shown until Karmalite supplies a current approved schedule.
    Service("botox_full_face", "بوتوكس", "Botox", *_INJECTABLES),
    Service("fillers", "فيلر للوجه والشفاه", "Dermal Fillers", *_INJECTABLES),
    Service("profhilo", "بروفايلو", "Profhilo", *_INJECTABLES),
    Service("skin_boosters", "محفزات البشرة / ميزوفيلر", "Skin Boosters / Mesofiller", *_INJECTABLES),

    Service("laser_full_body_women", "إزالة شعر الجسم بالليزر — سيدات", "Body Laser Hair Removal — Women", *_LASER, gender="female"),
    Service("laser_full_body_men", "إزالة شعر الجسم بالليزر — رجال", "Body Laser Hair Removal — Men", *_LASER, gender="male"),
    Service("laser_single_area", "إزالة شعر منطقة واحدة بالليزر", "Single-Area Laser Hair Removal", *_LASER),
    Service("laser_tattoo_removal", "إزالة الوشم بالليزر", "Laser Tattoo Removal", *_LASER),

    Service("hydrafacial", "هيدرافيشل / عناية طبية للوجه", "Hydrafacial / Medical Facial", *_SKIN),
    Service("dermapen", "ديرمابن", "Dermapen Microneedling", *_SKIN),
    Service("microneedling_rf", "فيفاس / وخز دقيق مع تردد راديوي", "Vivace / Microneedling RF", *_SKIN),
    Service("fractional_co2", "ليزر CO2 / فراكشنال", "CO2 / Fractional Laser", *_SKIN),
    Service("endermolift", "إندرمولفت LPG للوجه", "LPG Endermolift", *_SKIN),
    Service("ultratone_face", "ألترا تون للوجه", "UltraTone Face", *_SKIN),
    Service("chemical_peel", "تقشير كيميائي", "Chemical Peel", *_SKIN),
    Service("hifu", "هايفو لشد الوجه", "HIFU Facial Lifting", *_SKIN),
    Service("prp_face", "بلازما PRP للوجه", "PRP for Face", *_SKIN),

    Service("prp", "بلازما PRP للشعر", "PRP for Hair", *_HAIR),
    Service("hair_mesotherapy", "ميزوثيرابي للشعر", "Hair Mesotherapy", *_HAIR),

    Service("lpg_body", "LPG لنحت القوام", "LPG Body Contouring", *_BODY),
    Service("cryolipolysis", "تجميد الدهون", "Cryolipolysis / Fat Freezing", *_BODY),
    Service("fat_freezing_360", "تجميد الدهون 360°", "360° Fat Freezing", *_BODY),
    Service("exilis", "إكزيليس لنحت الجسم", "Exilis Body Sculpting", *_BODY),
    Service("emsculpt", "تقوية العضلات BTL", "BTL Muscle Strengthening", *_BODY),
    Service("ultratone_body", "ألترا تون للجسم", "UltraTone Body", *_BODY),
    Service("carboxy_therapy", "كربوكسي ثيرابي", "Carboxy Therapy", *_BODY),
    Service("body_peel", "تقشير كيميائي للجسم", "Body Chemical Peel", *_BODY),

    Service("spray_tan", "سبراي تان", "Spray Tan", *_TANNING),
    Service("solarium", "سولاريوم", "Solarium", *_TANNING),

    # الاستشارة مع طبيب مسمّى تُعرض باسم الطبيب فقط، بدون ذكر التخصص —
    # الاسم يكفي للحجز، وإظهار التخصص بقائمة قد تُقرأ من شاشة المريضة مساس بخصوصيتها.
    Service("gynecology_consultation", "استشارة مع د. رنا حداد", "Consultation with Dr. Rana Haddad", *_KARMAFEMME, gender="female"),
    Service("pregnancy_postpartum", "متابعة الحمل وما بعد الولادة", "Pregnancy & Postpartum Care", *_KARMAFEMME, gender="female"),
    Service("intimate_wellness", "استشارة العافية الحميمة", "Intimate Wellness Consultation", *_KARMAFEMME, gender="female"),
    Service("aesthetic_gynecology", "استشارة التجميل النسائي", "Aesthetic Gynecology Consultation", *_KARMAFEMME, gender="female"),

    Service("plastic_surgery_consultation", "استشارة جراحة تجميلية وترميمية", "Plastic & Reconstructive Surgery Consultation", *_SURGERY),
    Service("aesthetic_surgery_consultation", "استشارة جراحة تجميلية", "Aesthetic Surgery Consultation", *_SURGERY),

    Service("dermatology_consultation", "استشارة جلدية", "Dermatology Consultation", *_OTHER),
    Service("consultation", "استشارة عامة مع الطبيب", "General Doctor Consultation", *_OTHER),
    Service("not_sure", "مش متأكد — بحتاج استشارة", "Not sure yet — I need advice", *_OTHER),
)

SERVICE_IDS: tuple[str, ...] = tuple(s.id for s in SERVICES)
_BY_ID = {s.id: s for s in SERVICES}


def get_service(service_id: str | None) -> Service | None:
    return _BY_ID.get(service_id or "")


def label(service_id: str | None, lang: str = "ar") -> str:
    """اسم الخدمة للعرض. لو القيمة مش من الكتالوج (بيانات قديمة) بنرجّعها كما هي."""
    service = get_service(service_id)
    if service is None:
        return service_id or ""
    return service.ar if lang == "ar" else service.en


def catalogue() -> list[dict]:
    return [s.to_dict() for s in SERVICES]
