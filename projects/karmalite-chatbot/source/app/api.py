"""واجهة HTTP — FastAPI. شغّلها بـ: python -m uvicorn app.api:app --reload"""

from __future__ import annotations

import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .config import get_settings
from .appointment_emails import queue_status_emails, send_appointment_email
from .db import close_pool, healthcheck
from .doctors import DOCTOR_IDS, assigned_doctor, catalogue as doctor_catalogue, doctor_can_do_service
from .engine import chat
from .ingest import ingest_path
from .memory import (
    dashboard_stats,
    find_conversation,
    get_appointment,
    get_history,
    list_appointments,
    list_escalations,
    list_leads,
    set_escalation_handled,
    update_appointment_details,
    update_appointment_status,
    update_lead_status,
)
from .josms import configuration_status as sms_configuration_status
from .notifications import (
    create_appointment_notification,
    list_notifications,
    mark_notification_sent,
    notify_clinic_cancellation,
    retry_notification,
    send_notification,
    send_pending_notifications,
)
from .mailer import is_valid_email
from .verification import verification_required
from .voice import ALLOWED_AUDIO_TYPES, VoiceDisabled, synthesize, transcribe
from .voice import is_enabled as voice_is_enabled
from .scheduling import (
    create_appointment,
    find_appointments,
    get_availability,
    next_available_slots,
    parse_reference,
    resolve_and_cancel,
    resolve_and_reschedule,
)
from .services import SERVICE_IDS, catalogue
from .services import label as service_label
from .text_utils import normalize_jordan_phone

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parents[1] / "web"

APPOINTMENT_STATUSES = {"requested", "confirmed", "cancelled", "rescheduled", "completed", "no_show"}
LEAD_STATUSES = {"new", "contacted", "booked", "lost"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    فحص جاهزية خفيف فقط.

    ما بنشغّل init_schema() هون عن قصد: هي خطوة ترحيل (DDL + أقفال حصرية على الجداول)
    بتاخد دقيقة ونص على قاعدة سحابية، وكانت بتعلّق إقلاع السيرفر قبل ما يفتح المنفذ.
    مكانها الصحيح أمر واعٍ:  python -m app.cli init
    """
    try:
        state = healthcheck()
        if state.get("database") == "ok":
            logger.info("قاعدة البيانات جاهزة — %s مقطع مفهرس", state.get("chunks", 0))
            if not state.get("chunks"):
                logger.warning("قاعدة المعرفة فاضية — شغّل: python -m app.cli ingest data")
        else:
            logger.error("قاعدة البيانات مش متصلة: %s", state.get("error"))
    except Exception as exc:  # pragma: no cover
        logger.error(
            "تعذّر فحص قاعدة البيانات (%s). لو الجداول مش موجودة شغّل: python -m app.cli init", exc
        )

    if not get_settings().admin_token:
        logger.warning("ADMIN_TOKEN مش محدد بـ .env — لوحة الأدمن رح ترفض كل الطلبات")
    yield
    close_pool()


app = FastAPI(title="Karmalite RAG Assistant", version="1.2.0", lifespan=lifespan)

# ملفات الواجهة الثابتة (الشعار والصور) — /static/logo.png
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


# ======================================================================
# النماذج
# ======================================================================
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    channel: str = "web"
    lang: str | None = Field(default=None, pattern="^(ar|en)$")


class IngestRequest(BaseModel):
    path: str = "data"
    force: bool = False


class AppointmentRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=120)
    phone: str = Field(min_length=7, max_length=25)
    email: str | None = Field(default=None, max_length=254)
    date: Date
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    service: str | None = Field(default=None, max_length=60)
    doctor_id: str | None = Field(default=None, max_length=60)
    gender: str = Field(default="unknown", pattern="^(male|female|unknown)$")

    @field_validator("service")
    @classmethod
    def _known_service(cls, value: str | None) -> str | None:
        if value and value not in SERVICE_IDS:
            raise ValueError("خدمة غير معروفة")
        return value

    @field_validator("doctor_id")
    @classmethod
    def _known_doctor(cls, value: str | None) -> str | None:
        if value and value not in DOCTOR_IDS:
            raise ValueError("طبيب غير معروف")
        return value

    notes: str | None = Field(default=None, max_length=500)
    session_id: str | None = None
    lang: str = Field(default="ar", pattern="^(ar|en)$")


class LookupRequest(BaseModel):
    """التحقق بعاملين: الاسم + الرقم. نفس الحدّ الأمني المستخدم بالشات."""

    full_name: str = Field(min_length=3, max_length=120)
    phone: str = Field(min_length=7, max_length=25)
    lang: str = Field(default="ar", pattern="^(ar|en)$")


class CancelRequest(LookupRequest):
    reference: str = Field(min_length=3, max_length=32)
    reason: str | None = Field(default=None, max_length=300)


class RescheduleRequest(LookupRequest):
    reference: str = Field(min_length=3, max_length=32)
    date: Date
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    notes: str | None = Field(default=None, max_length=500)


class StatusUpdate(BaseModel):
    status: str


class EditAppointmentRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=120)
    phone: str | None = Field(default=None, min_length=7, max_length=25)
    email: str | None = Field(default=None, max_length=254)
    date: Date | None = None
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    service: str | None = Field(default=None, max_length=60)
    doctor_id: str | None = Field(default=None, max_length=60)
    gender: str | None = Field(default=None, pattern="^(male|female|unknown)$")
    notes: str | None = Field(default=None, max_length=500)


class HandledUpdate(BaseModel):
    handled: bool = True


# ======================================================================
# حماية لوحة الأدمن
# ======================================================================
def require_admin(x_admin_token: str = Header(default="")) -> None:
    """
    حماية بسيطة بتوكن ثابت. كفاية لعيادة على شبكة داخلية،
    بس لو رح تعرّض اللوحة على الإنترنت حطها خلف مصادقة حقيقية (OAuth / SSO).
    """
    token = get_settings().admin_token
    if not token:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN مش محدد بملف .env")
    if not secrets.compare_digest(x_admin_token, token):  # مقارنة ثابتة الزمن
        raise HTTPException(status_code=401, detail="توكن غير صحيح")




# ======================================================================
# الصفحات
# ======================================================================
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return FileResponse(WEB_DIR / "admin.html")


# ======================================================================
# عام
# ======================================================================
@app.get("/health")
def health() -> dict:
    """ما بيرمي خطأ — بيرجّع الحالة عشان الواجهة تعرض رسالة مفهومة."""
    try:
        return {
            **healthcheck(),
            "sms": sms_configuration_status(),
            "voice": voice_is_enabled(),
            # مفيد للتشخيص: تعديل .env ما بيعيد تحميل العملية، فالسيرفر الشغّال
            # ممكن يكون لسا شايف الإعداد القديم لحد ما ينعمل ريستارت
            "email_verification": verification_required(),
        }
    except Exception as exc:
        logger.warning("healthcheck فشل: %s", exc)
        return {"database": "unavailable", "pgvector": False, "chunks": 0, "error": str(exc)}


@app.post("/chat")
def chat_endpoint(request: ChatRequest) -> dict:
    session_id = request.session_id or f"web-{uuid.uuid4().hex[:12]}"
    try:
        result = chat(
            request.message,
            session_id=session_id,
            channel=request.channel,
            lang=request.lang,
        )
    except Exception as exc:
        logger.exception("chat فشل")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.to_dict()


# ======================================================================
# الصوت
# ======================================================================
@app.post("/voice/transcribe")
async def voice_transcribe(
    audio: UploadFile = File(...),
    lang: str | None = Form(default=None),
) -> dict:
    """
    كلام → نص. الواجهة بتبعت التسجيل، وبترجعله النص عشان تبعته كرسالة عادية.

    مقصود إنه ما يحجز ولا ينفّذ شي بنفسه: النص بيرجع للواجهة، والواجهة
    بتمرّره على `/chat` — فأي حجز بيعدّي على نفس أدوات الشات وحواجزها.
    """
    if not voice_is_enabled():
        raise HTTPException(status_code=503, detail="خاصية الصوت مطفية")

    settings = get_settings()
    ctype = (audio.content_type or "").split(";")[0].strip().lower()
    if ctype and ctype not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail=f"صيغة صوت غير مدعومة: {ctype}")

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=422, detail="التسجيل فاضي")
    limit_bytes = int(settings.voice_max_upload_mb * 1024 * 1024)
    if len(data) > limit_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"التسجيل أكبر من الحد ({settings.voice_max_upload_mb:.0f} ميغا)",
        )

    try:
        text = transcribe(data, filename=audio.filename or "audio.webm", lang=lang)
    except VoiceDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("تفريغ الصوت فشل")
        raise HTTPException(status_code=502, detail="تعذّر تحويل الصوت لنص") from exc

    return {"text": text, "chars": len(text)}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    lang: str = Field(default="ar", pattern="^(ar|en)$")


@app.post("/voice/speak")
def voice_speak(request: SpeakRequest) -> Response:
    """نص → كلام. بيرجّع ملف صوتي جاهز للتشغيل بالمتصفح."""
    if not voice_is_enabled():
        raise HTTPException(status_code=503, detail="خاصية الصوت مطفية")
    try:
        audio, mime = synthesize(request.text, lang=request.lang)
    except VoiceDisabled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("توليد الصوت فشل")
        raise HTTPException(status_code=502, detail="تعذّر توليد الصوت") from exc

    return Response(
        content=audio,
        media_type=mime,
        headers={"Cache-Control": "no-store", "Content-Length": str(len(audio))},
    )


@app.get("/history")
def history_endpoint(session_id: str, limit: int = 40) -> dict:
    """
    سجل المحادثة السابق لنفس الجلسة — عشان الشات يكمل من وين وقف بعد إعادة التحميل.
    الـ session_id رمز عشوائي محفوظ بمتصفح المستخدم، ما بيدل على هوية.
    """
    conversation_id = find_conversation(session_id)
    if conversation_id is None:
        return {"session_id": session_id, "messages": []}
    return {
        "session_id": session_id,
        "messages": get_history(conversation_id, turns=max(1, min(limit, 100)) // 2),
    }


@app.post("/my-appointments")
def my_appointments(request: LookupRequest) -> dict:
    """مواعيد العميل القادمة بعد التحقق من الاسم والرقم."""
    phone = normalize_jordan_phone(request.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="رقم الهاتف غير صالح — استخدم صيغة 07XXXXXXXX")
    found = find_appointments(phone, request.full_name.strip())
    for item in found:
        item["service_label_ar"] = service_label(item.get("service"), "ar")
        item["service_label_en"] = service_label(item.get("service"), "en")
    return {"appointments": found}


@app.get("/next-slots")
def next_slots(gender: str = "unknown", limit: int = 6) -> dict:
    """أقرب المواعيد المتاحة — تُعرض بعد الإلغاء ليحجز العميل بديلاً بضغطة."""
    if gender not in {"male", "female", "unknown"}:
        gender = "unknown"
    return {"slots": next_available_slots(gender, limit=max(1, min(limit, 12)))}


@app.post("/appointments/reschedule")
def reschedule_endpoint(request: RescheduleRequest, background_tasks: BackgroundTasks) -> dict:
    try:
        slot = datetime.strptime(request.time, "%H:%M").time()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="صيغة الوقت غير صحيحة") from exc

    result = resolve_and_reschedule(
        full_name=request.full_name.strip(),
        phone_raw=request.phone,
        reference=request.reference,
        new_date=request.date,
        new_time=slot,
        notes=request.notes,
    )
    if result["ok"]:
        appointment_id = parse_reference(result["reference"])
        notice = create_appointment_notification(
            appointment_id, "appointment_rescheduled", lang=request.lang
        )
        if notice and notice["created"]:
            background_tasks.add_task(send_notification, notice["notification_id"])
            result["notification"] = {
                "id": notice["notification_id"], "status": notice["status"]
            }
        return result
    _raise_appointment_error(result)


@app.post("/appointments/cancel")
def cancel_endpoint(request: CancelRequest, background_tasks: BackgroundTasks) -> dict:
    result = resolve_and_cancel(
        full_name=request.full_name.strip(),
        phone_raw=request.phone,
        reference=request.reference,
        reason=request.reason,
        by="self-service",
    )
    if result["ok"]:
        appointment_id = parse_reference(result["reference"])
        notice = create_appointment_notification(
            appointment_id, "patient_cancelled", lang=request.lang
        )
        if notice and notice["created"]:
            background_tasks.add_task(send_notification, notice["notification_id"])
            result["notification"] = {
                "id": notice["notification_id"], "status": notice["status"]
            }
        return result
    _raise_appointment_error(result)


def _raise_appointment_error(result: dict) -> None:
    """ترجمة رموز أخطاء الجدولة لأكواد HTTP ورسائل للعميل."""
    status = {
        "invalid_name": 422, "invalid_phone": 422,
        "no_appointments": 404, "not_found": 404,
        "verification_failed": 403, "ambiguous": 409,
    }.get(result["error"], 409)
    detail = {
        "invalid_name": "الاسم غير مكتمل",
        "invalid_phone": "رقم الهاتف غير صالح",
        "no_appointments": "ما في مواعيد قادمة بهالاسم والرقم",
        "not_found": "الموعد غير موجود",
        "verification_failed": "البيانات ما بتطابق هذا الموعد",
        "ambiguous": "اختر الموعد المطلوب",
        "already_cancelled": "هذا الموعد ملغي أصلاً",
        "already_completed": "هذا الموعد تم تنفيذه",
        "already_no_show": "هذا الموعد مسجّل كعدم حضور",
        "already_passed": "وقت هذا الموعد مضى",
        "slot_taken": "هذا الوقت لم يعد متاحاً — اختر وقتاً آخر",
        "same_slot": "هذا هو وقت موعدك الحالي — اختر وقتاً مختلفاً",
    }.get(result["error"], result["error"])
    raise HTTPException(status_code=status, detail=detail)


@app.post("/ingest")
def ingest_endpoint(request: IngestRequest) -> dict:
    try:
        return {"results": ingest_path(request.path, force=request.force)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ======================================================================
# المواعيد (عام — للزبون)
# ======================================================================
@app.get("/contact")
def contact() -> dict:
    """أرقام العيادة — تستخدمها الواجهة لتحويلها لروابط اتصال داخل الشات."""
    settings = get_settings()
    return {"clinic_phone": settings.clinic_phone, "emergency_phone": settings.emergency_phone}


@app.get("/services")
def services() -> dict:
    """كتالوج الخدمات — تستخدمه لوحة الأدمن بعرض وتعديل الخدمة."""
    return {"services": catalogue()}


@app.get("/doctors")
def doctors() -> dict:
    return {"doctors": doctor_catalogue()}


@app.get("/availability")
def availability(
    date: Date,
    gender: str = "unknown",
    service: str | None = None,
    doctor_id: str | None = None,
    phone: str | None = None,
) -> dict:
    """
    أوقات طلب الموعد العامة؛ لا تمثل جدول طبيب محدد أو ساعات رجال غير معتمدة.

    `service` مهم: الخانة الواحدة بتستوعب خدمات مختلفة بنفس الوقت، فبدونها
    بترجع كل أوقات الدوام. `phone` بيشيل الأوقات اللي هذا الشخص محجوزها أصلاً.
    """
    if gender not in {"male", "female", "unknown"}:
        gender = "unknown"
    if service and service not in SERVICE_IDS:
        raise HTTPException(status_code=422, detail="خدمة غير معروفة")
    if doctor_id and doctor_id not in DOCTOR_IDS:
        raise HTTPException(status_code=422, detail="طبيب غير معروف")
    if doctor_id and not doctor_can_do_service(doctor_id, service):
        raise HTTPException(status_code=422, detail="الطبيب لا يقدم هذه الخدمة")
    return get_availability(
        date, gender,
        service=service,
        phone=normalize_jordan_phone(phone) if phone else None,
        doctor_id=doctor_id,
    ).to_dict()


# رسائل تعارض الحجز — نفس رموز create_appointment، مترجَمة للواجهة
_APPOINTMENT_CONFLICT = {
    "service_taken": "هذه الخدمة محجوزة بهذا الوقت — اختر وقتاً آخر",
    "already_booked_this_slot": "عندك موعد بنفس التاريخ والوقت",
    "too_many_active": "وصلت الحد الأقصى للمواعيد القادمة — تواصل مع الاستقبال",
    "rate_limited": "محاولات حجز كثيرة خلال وقت قصير — جرّب بعد شوي",
    "doctor_taken": "الطبيب محجوز بهذا الوقت — اختر وقتاً آخر",
    "doctor_not_eligible": "الطبيب المطلوب لا يقدم هذه الخدمة",
}


@app.post("/appointments")
def request_appointment(request: AppointmentRequest, background_tasks: BackgroundTasks) -> dict:
    phone = normalize_jordan_phone(request.phone)
    if not phone:
        raise HTTPException(status_code=422, detail="رقم الهاتف غير صالح — استخدم صيغة 07XXXXXXXX")
    try:
        slot = datetime.strptime(request.time, "%H:%M").time()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="صيغة الوقت غير صحيحة") from exc
    if request.doctor_id and not doctor_can_do_service(request.doctor_id, request.service):
        raise HTTPException(status_code=422, detail="الطبيب المطلوب لا يقدم هذه الخدمة")

    # التحقق من التوفر على السيرفر — الواجهة ممكن تكون بايتة أو متلاعب فيها.
    # بنمرّر الخدمة والرقم عشان القواعد الجديدة تنطبق (خدمة لكل خانة، وشخص واحد مرة).
    available = get_availability(
        request.date, request.gender, service=request.service, phone=phone,
        doctor_id=request.doctor_id,
    ).slots
    if request.time not in available:
        raise HTTPException(status_code=409, detail="هذا الوقت لم يعد متاحاً — اختر وقتاً آخر")

    result = create_appointment(
        full_name=request.full_name.strip(),
        phone=phone,
        day=request.date,
        slot=slot,
        service=request.service,
        gender=request.gender,
        notes=request.notes,
        email=(request.email or "").strip().lower() or None,
        doctor_id=request.doctor_id,
    )
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=_APPOINTMENT_CONFLICT.get(
            result["error"], "هذا الوقت لم يعد متاحاً — اختر وقتاً آخر"
        ))
    notice = create_appointment_notification(
        result["appointment_id"], "appointment_requested", lang=request.lang
    )
    if notice and notice["created"]:
        background_tasks.add_task(send_notification, notice["notification_id"])
        result["notification"] = {
            "id": notice["notification_id"], "status": notice["status"]
        }
    return result


# ======================================================================
# لوحة الأدمن
# ======================================================================
@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats() -> dict:
    return dashboard_stats()


@app.get("/api/admin/appointments", dependencies=[Depends(require_admin)])
def admin_appointments(
    status: str | None = None,
    limit: int = 200,
    date_from: Date | None = None,
    date_to: Date | None = None,
    time_from: Time | None = None,
    time_to: Time | None = None,
) -> dict:
    """
    قائمة المواعيد للوحة. كل حدود المدى اختيارية ومستقلة:
    ممكن تبعت `date_from` لحاله، أو `time_from` + `time_to` بدون تاريخ، وهكذا.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="تاريخ «من» بعد تاريخ «إلى» — بدّل بينهم")
    if time_from and time_to and time_from > time_to:
        raise HTTPException(status_code=422, detail="وقت «من» بعد وقت «إلى» — بدّل بينهم")

    return {
        "appointments": list_appointments(
            status=status,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            time_from=time_from,
            time_to=time_to,
        )
    }


@app.patch("/api/admin/appointments/{appointment_id}", dependencies=[Depends(require_admin)])
def admin_update_appointment(
    appointment_id: int, update: StatusUpdate, background_tasks: BackgroundTasks
) -> dict:
    if update.status not in APPOINTMENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"حالة غير معروفة: {update.status}")
    update_result = update_appointment_status(appointment_id, update.status, by="admin")
    if update_result == "too_early":
        raise HTTPException(
            status_code=409,
            detail="لا يمكن تسجيل الموعد كمكتمل أو عدم حضور قبل حلول تاريخه ووقته",
        )
    if update_result == "not_found":
        raise HTTPException(status_code=404, detail="الموعد غير موجود")

    response = {"ok": True, "id": appointment_id, "status": update.status}

    email_events = queue_status_emails(appointment_id, update.status)
    if email_events:
        response["emails"] = [
            {"id": event["id"], "kind": event["kind"], "status": event["status"]}
            for event in email_events
        ]
        for event in email_events:
            background_tasks.add_task(send_appointment_email, event["id"])

    # التأكيد أو الإلغاء من العيادة يولّد رسالة خدمية مستقلة عن نجاح بوابة SMS.
    if update.status in {"confirmed", "cancelled"}:
        notice = (
            notify_clinic_cancellation(appointment_id)
            if update.status == "cancelled"
            else create_appointment_notification(appointment_id, "appointment_confirmed")
        )
        if notice:
            response["notification"] = {
                "id": notice["notification_id"],
                "status": notice["status"],
                "slots": notice["slots"],
                "delivered_to_chat": notice["delivered_to_chat"],
                "body_ar": notice["body_ar"],
            }
            if notice["created"]:
                background_tasks.add_task(send_notification, notice["notification_id"])
    return response


@app.put("/api/admin/appointments/{appointment_id}", dependencies=[Depends(require_admin)])
def admin_edit_appointment(appointment_id: int, edit: EditAppointmentRequest) -> dict:
    """تعديل تفاصيل الموعد (الاسم، الهاتف، التاريخ، الوقت، الخدمة، الجنس، الملاحظات)."""
    fields = {}
    if edit.full_name is not None:
        fields["full_name"] = edit.full_name.strip()
    if edit.phone is not None:
        phone = normalize_jordan_phone(edit.phone)
        if not phone:
            raise HTTPException(status_code=422, detail="رقم الهاتف غير صالح")
        fields["phone"] = phone
    if edit.email is not None:
        cleaned = edit.email.strip().lower()
        if cleaned and not is_valid_email(cleaned):
            raise HTTPException(status_code=422, detail="صيغة الإيميل غير صحيحة")
        fields["email"] = cleaned or None
    if edit.date is not None:
        fields["appointment_date"] = edit.date
    if edit.time is not None:
        fields["appointment_time"] = edit.time
    if edit.service is not None:
        if edit.service not in SERVICE_IDS:
            raise HTTPException(status_code=422, detail="خدمة غير معروفة")
        fields["service"] = edit.service
    if edit.doctor_id is not None:
        if edit.doctor_id not in DOCTOR_IDS:
            raise HTTPException(status_code=422, detail="طبيب غير معروف")
        service_id = edit.service
        if service_id is None:
            current = get_appointment(appointment_id)
            service_id = current["service"] if current else None
        if not doctor_can_do_service(edit.doctor_id, service_id):
            raise HTTPException(status_code=422, detail="الطبيب لا يقدم هذه الخدمة")
        fields["doctor_id"] = edit.doctor_id
    elif edit.service is not None:
        doctor = assigned_doctor(edit.service)
        fields["doctor_id"] = doctor.id if doctor else None
    if edit.gender is not None:
        fields["gender"] = edit.gender
    if edit.notes is not None:
        fields["notes"] = edit.notes
    if not fields:
        raise HTTPException(status_code=422, detail="لا يوجد حقول للتعديل")
    if not update_appointment_details(appointment_id, **fields):
        raise HTTPException(status_code=404, detail="الموعد غير موجود")
    return {"ok": True, "id": appointment_id}


@app.get("/api/admin/notifications", dependencies=[Depends(require_admin)])
def admin_notifications(status: str | None = "pending", limit: int = 50) -> dict:
    """صادر الرسائل مع حالة الإرسال الآلية عبر JOSMS."""
    return {"notifications": list_notifications(status=status, limit=limit)}


@app.get("/api/admin/sms/status", dependencies=[Depends(require_admin)])
def admin_sms_status() -> dict:
    """جاهزية الربط بدون كشف اسم الحساب أو كلمة المرور."""
    return sms_configuration_status()


@app.post("/api/admin/notifications/{notification_id}/send", dependencies=[Depends(require_admin)])
def admin_send_notification(notification_id: int, background_tasks: BackgroundTasks) -> dict:
    if not retry_notification(notification_id):
        raise HTTPException(
            status_code=409,
            detail="الإشعار غير موجود أو سبق تقديمه للبوابة؛ لن نرسله مرتين",
        )
    background_tasks.add_task(send_notification, notification_id)
    return {"ok": True, "id": notification_id, "status": "pending"}


@app.post("/api/admin/notifications/send-pending", dependencies=[Depends(require_admin)])
def admin_send_pending(background_tasks: BackgroundTasks, limit: int = 20) -> dict:
    limit = max(1, min(limit, 100))
    background_tasks.add_task(send_pending_notifications, limit)
    return {"ok": True, "queued": True, "limit": limit}


@app.patch("/api/admin/notifications/{notification_id}", dependencies=[Depends(require_admin)])
def admin_mark_sent(notification_id: int) -> dict:
    if not mark_notification_sent(notification_id):
        raise HTTPException(status_code=404, detail="الإشعار غير موجود")
    return {"ok": True, "id": notification_id, "status": "sent"}


@app.get("/api/admin/leads", dependencies=[Depends(require_admin)])
def admin_leads(status: str | None = None, limit: int = 200) -> dict:
    return {"leads": list_leads(status=status, limit=limit)}


@app.patch("/api/admin/leads/{lead_id}", dependencies=[Depends(require_admin)])
def admin_update_lead(lead_id: int, update: StatusUpdate) -> dict:
    if update.status not in LEAD_STATUSES:
        raise HTTPException(status_code=422, detail=f"حالة غير معروفة: {update.status}")
    if not update_lead_status(lead_id, update.status):
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    return {"ok": True, "id": lead_id, "status": update.status}


@app.get("/api/admin/escalations", dependencies=[Depends(require_admin)])
def admin_escalations(handled: bool = False, limit: int = 100) -> dict:
    return {"escalations": list_escalations(handled=handled, limit=limit)}


@app.patch("/api/admin/escalations/{escalation_id}", dependencies=[Depends(require_admin)])
def admin_update_escalation(escalation_id: int, update: HandledUpdate) -> dict:
    if not set_escalation_handled(escalation_id, update.handled):
        raise HTTPException(status_code=404, detail="التصعيد غير موجود")
    return {"ok": True, "id": escalation_id, "handled": update.handled}


# ======================================================================
# توافق للخلف (الروابط القديمة)
# ======================================================================
@app.get("/leads", dependencies=[Depends(require_admin)], include_in_schema=False)
def leads_endpoint(status: str | None = None, limit: int = 50) -> dict:
    return {"leads": list_leads(status=status, limit=limit)}


@app.get("/escalations", dependencies=[Depends(require_admin)], include_in_schema=False)
def escalations_endpoint(handled: bool = False, limit: int = 50) -> dict:
    return {"escalations": list_escalations(handled=handled, limit=limit)}
