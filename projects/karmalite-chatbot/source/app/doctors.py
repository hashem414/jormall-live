"""Authoritative doctor roster, service eligibility, and automatic assignment."""

from __future__ import annotations

from dataclasses import dataclass

from .services import SERVICE_IDS


@dataclass(frozen=True)
class Doctor:
    id: str
    name: str
    summary: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "summary": self.summary}


DOCTORS: tuple[Doctor, ...] = (
    Doctor(
        "miral",
        "Dr. Miral Al Nimri",
        "Professional, attentive to patient concerns, and focused on appropriate treatment without unnecessary services.",
    ),
    Doctor(
        "qasim_wreikat",
        "Dr. Qasim Wreikat",
        "Clear and reassuring, with thorough explanations of treatments including scar care and cortisone injections.",
    ),
    Doctor(
        "leen",
        "Dr. Leen",
        "A naturopathic doctor with a holistic approach to hormonal balance, digestion, fatigue, and stress.",
    ),
    Doctor(
        "adeeb",
        "Dr. Adeeb Halasa",
        "Provides clear explanations and natural-looking cosmetic results, including Botox.",
    ),
)

DOCTOR_IDS: tuple[str, ...] = tuple(d.id for d in DOCTORS)
_BY_ID = {d.id: d for d in DOCTORS}

_INJECTABLES = {"botox_full_face", "fillers", "profhilo", "skin_boosters"}
_LASER_SKIN_HAIR = {
    "laser_full_body_women", "laser_full_body_men", "laser_single_area",
    "laser_tattoo_removal", "hydrafacial", "dermapen", "microneedling_rf",
    "fractional_co2", "endermolift", "ultratone_face", "chemical_peel", "hifu",
    "prp_face", "prp", "hair_mesotherapy", "dermatology_consultation",
}
_BODY_AESTHETICS = {
    "lpg_body", "cryolipolysis", "fat_freezing_360", "exilis", "emsculpt",
    "ultratone_body", "carboxy_therapy", "body_peel", "spray_tan", "solarium",
}
_SURGERY = {"plastic_surgery_consultation", "aesthetic_surgery_consultation"}
_WELLNESS = {
    "gynecology_consultation", "pregnancy_postpartum", "intimate_wellness",
    "aesthetic_gynecology", "consultation", "not_sure",
}
_CONSULTATIONS = {
    service for service in SERVICE_IDS
    if service.endswith("_consultation") or service in {"consultation", "not_sure"}
}

_DEFAULT_DOCTOR = {
    **{service: "adeeb" for service in _INJECTABLES | _BODY_AESTHETICS},
    **{service: "miral" for service in _LASER_SKIN_HAIR},
    **{service: "qasim_wreikat" for service in _SURGERY},
    **{service: "leen" for service in _WELLNESS},
}

_CLINICAL_SCOPE = {
    "miral": _LASER_SKIN_HAIR | _INJECTABLES,
    "qasim_wreikat": _SURGERY,
    "leen": _WELLNESS,
    "adeeb": _INJECTABLES | _BODY_AESTHETICS | _SURGERY,
}

assert set(_DEFAULT_DOCTOR) == set(SERVICE_IDS), "Every service needs a default doctor"


def catalogue() -> list[dict]:
    return [
        {
            **doctor.to_dict(),
            "service_ids": [
                service_id for service_id in SERVICE_IDS
                if doctor_can_do_service(doctor.id, service_id)
            ],
        }
        for doctor in DOCTORS
    ]


def get_doctor(doctor_id: str | None) -> Doctor | None:
    return _BY_ID.get(doctor_id or "")


def eligible_doctors(service_id: str | None) -> tuple[Doctor, ...]:
    if service_id in _CONSULTATIONS:
        return DOCTORS
    return tuple(d for d in DOCTORS if service_id in _CLINICAL_SCOPE[d.id])


def doctor_can_do_service(doctor_id: str, service_id: str | None) -> bool:
    return any(d.id == doctor_id for d in eligible_doctors(service_id))


def assigned_doctor(service_id: str | None, requested_doctor_id: str | None = None) -> Doctor | None:
    if requested_doctor_id:
        doctor = get_doctor(requested_doctor_id)
        if doctor and doctor_can_do_service(doctor.id, service_id):
            return doctor
        return None
    return get_doctor(_DEFAULT_DOCTOR.get(service_id or ""))
