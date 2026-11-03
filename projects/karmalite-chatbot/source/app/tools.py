"""
أدوات الموديل (Function Calling).

الأدوات هي اللي بتحوّل البوت من «مجاوب» لـ «موظف بيشتغل»:
بتخزّن العميل المحتمل بقاعدة البيانات، وبتفتح تذكرة تصعيد للطوارئ والشكاوى.
"""

from __future__ import annotations

import json
import logging
from datetime import date as Date
from datetime import datetime

from .config import get_settings
from .db import get_conn
from .doctors import DOCTOR_IDS, assigned_doctor, doctor_can_do_service, get_doctor
from .location import describe as describe_location
from .location import is_configured as location_configured
from .mailer import is_valid_email, normalize_email
from .verification import check_code, is_verified, issue_code, verification_required
from .scheduling import (
    OFFER_LEAD_MINUTES,
    create_appointment,
    find_appointments,
    get_availability,
    next_available_slots,
    resolve_and_cancel,
)
from .services import SERVICE_IDS, get_service
from .services import label as service_label
from .text_utils import format_phone_display, normalize_jordan_phone

logger = logging.getLogger(__name__)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "capture_lead",
            "description": (
                "سجّل بيانات عميل محتمل ليتواصل معه فريق الاستقبال ويثبّت الموعد. "
                "استدعها فقط بعد الحصول على الاسم الكامل ورقم الهاتف معاً من العميل نفسه. "
                "ممنوع تخمين أو تلفيق أي حقل."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "full_name": {
                        "type": "string",
                        "description": "الاسم الكامل كما ذكره العميل حرفياً",
                    },
                    "phone": {
                        "type": "string",
                        "description": "رقم الهاتف كما كتبه العميل، مثال: 0791234567",
                    },
                    "service_interest": {
                        "type": "string",
                        "description": "الخدمة التي يسأل عنها العميل، إن وُجدت",
                    },
                    "preferred_time": {
                        "type": "string",
                        "description": "الوقت أو اليوم المفضل للاتصال أو الموعد، إن ذُكر",
                    },
                    "gender": {
                        "type": "string",
                        "enum": ["male", "female", "unknown"],
                        "description": "جنس العميل إن أمكن استنتاجه، وإلا unknown",
                    },
                    "notes": {
                        "type": "string",
                        "description": "أي ملاحظة مفيدة للاستقبال (سؤال طبي، طلب خاص...)",
                    },
                },
                "required": ["full_name", "phone"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "اعرض الأوقات المتاحة فعلياً للحجز. استدعها فور ما يعبّر العميل عن رغبته بحجز موعد "
                "أو يسأل عن الأوقات المتاحة. "
                "مرّر `date` إذا حدّد يوماً معيناً، واتركها فاضية عشان تاخد أقرب الأوقات المتاحة بالأيام الجاية. "
                "🔒 **ممنوع تقترح أي وقت من عندك** — اعرض فقط الأوقات اللي بترجعها هذه الأداة حرفياً."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": (
                            "اليوم المطلوب بصيغة YYYY-MM-DD. احسبه من تاريخ اليوم المذكور بالبرومبت "
                            "لما يقول «بكرا» أو «يوم الأحد». اتركه فاضي لأقرب الأوقات المتاحة."
                        ),
                    },
                    "service": {
                        "type": "string",
                        "enum": list(SERVICE_IDS),
                        "description": (
                            "معرّف الخدمة اللي بدّه ياها. **مهم جداً**: الخانة الواحدة بتستوعب "
                            "أكثر من مريض بنفس الوقت ما دامت الخدمة مختلفة، فالتوفر بيختلف "
                            "من خدمة لخدمة. اسأل عن الخدمة **قبل** ما تعرض أوقات، ومرّرها هون "
                            "عشان الأوقات تكون دقيقة."
                        ),
                    },
                    "doctor_id": {
                        "type": "string",
                        "enum": list(DOCTOR_IDS),
                        "description": (
                            "الطبيب الذي طلبه العميل صراحةً. اتركه فارغاً إذا لم يطلب طبيباً؛ "
                            "النظام يعيّن طبيباً مناسباً للخدمة تلقائياً."
                        ),
                    },
                    "gender": {
                        "type": "string",
                        "enum": ["male", "female", "unknown"],
                        "description": "جنس العميل إن عُرف؛ لا يفتح ساعات دوام غير معتمدة",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email_code",
            "description": (
                "ابعت رمز تحقق على إيميل العميل. استدعها بعد ما تاخد **الاسم والرقم والإيميل** "
                "وقبل `book_appointment` مباشرة. بعدها اطلب منه الرمز اللي وصله."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "الإيميل كما كتبه العميل بالرسالة الحالية",
                    },
                },
                "required": ["email"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_email_code",
            "description": (
                "تحقّق من الرمز اللي كتبه العميل. استدعها لما يعطيك رمزاً مكوّناً من ٦ أرقام. "
                "لازم ترجع ok=true قبل ما تقدر تستدعي `book_appointment`."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "نفس الإيميل اللي انبعتله الرمز",
                    },
                    "code": {
                        "type": "string",
                        "description": "الرمز المكوّن من ٦ أرقام كما كتبه العميل",
                    },
                },
                "required": ["email", "code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "سجّل **طلب** موعد بوقت محدد اختاره العميل من نتيجة `check_availability`. "
                "استدعها فقط بعد ما يتوفر عندك: الوقت اللي اختاره + اسمه الكامل + رقم هاتفه. "
                "بعد نجاح تحقق الإيميل استخدم الاسم والرقم اللذين أعطاهما العميل قبل الرمز؛ لا تطلبهما ثانية. "
                "ممنوع تخمّن أي حقل، وممنوع تحجز وقت ما ظهر بنتيجة `check_availability`."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "full_name": {
                        "type": "string",
                        "description": "الاسم الكامل كما ذكره العميل حرفياً",
                    },
                    "phone": {
                        "type": "string",
                        "description": "رقم الهاتف كما كتبه العميل، مثال: 0791234567",
                    },
                    "email": {
                        "type": "string",
                        "description": (
                            "إيميل العميل — نفس الإيميل اللي تحقّقت منه بـ `verify_email_code`. "
                            "مطلوب لما يكون التحقق بالبريد مفعّلاً."
                        ),
                    },
                    "date": {
                        "type": "string",
                        "description": "تاريخ الموعد بصيغة YYYY-MM-DD، منسوخ من نتيجة check_availability",
                    },
                    "time": {
                        "type": "string",
                        "description": (
                            "وقت الموعد بصيغة HH:MM بنظام ٢٤ ساعة، منسوخ **حرفياً** "
                            "من قائمة الأوقات المتاحة اللي رجعتها check_availability. "
                            "⚠ لازم يكون **الوقت اللي اختاره العميل بنفسه**. إذا كان آخر شي صار "
                            "إنك عرضت عليه بدائل وما اختار وحدة منها (أعطاك اسمه ورقمه بس)، "
                            "**لا تستدعِ هذه الأداة أصلاً** — اسأله يختار وقتاً أول. "
                            "ممنوع تختار عنه ولو كان أقرب وقت متاح."
                        ),
                    },
                    "service": {
                        "type": "string",
                        "enum": list(SERVICE_IDS),
                        "description": (
                            "معرّف الخدمة اللي طلبها العميل. **إلزامي** — لازم تسأله عن الخدمة "
                            "قبل الحجز ولا تخمّنها. "
                            "⚠ `not_sure` مسموحة **فقط** إذا العميل قال صراحةً إنه مش متأكد أو "
                            "بدّه استشارة أول. إذا سألته عن الخدمة وما جاوبك، اسأله مرة تانية "
                            "ولا تستدعي هذه الأداة — السكوت مش موافقة على `not_sure`."
                        ),
                    },
                    "doctor_id": {
                        "type": "string",
                        "enum": list(DOCTOR_IDS),
                        "description": (
                            "الطبيب الذي اختاره العميل صراحةً. لا تخمّنه ولا تسأل عنه إذا لم يذكر تفضيلاً. "
                            "النظام يرفض الطبيب إذا كانت الخدمة خارج نطاقه، ويعيّن طبيباً مناسباً تلقائياً عند تركه فارغاً."
                        ),
                    },
                    "gender": {
                        "type": "string",
                        "enum": ["male", "female", "unknown"],
                        "description": "جنس العميل إن عُرف، وإلا unknown",
                    },
                    "notes": {
                        "type": "string",
                        "description": "أي ملاحظة مفيدة للاستقبال (طبيب مفضل، طلب خاص...)",
                    },
                },
                "required": ["full_name", "phone", "date", "time", "service"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_location",
            "description": (
                "أرسل للعميل بطاقة موقع العيادة (الشارع، المبنى، الطابق، ورابط الخرائط). "
                "استدعها فور ما يسأل «وين موقعكم» أو «كيف بوصل» أو يطلب العنوان أو اللوكيشن، "
                "وكمان بعد تأكيد أي طلب موعد لتسهيل الوصول."
            ),
            "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_my_appointments",
            "description": (
                "ابحث عن مواعيد العميل القادمة للتعديل أو الإلغاء. "
                "لازم تاخد منه **الاسم الكامل ورقم الهاتف** اللي حجز فيهم قبل ما تستدعيها. "
                "ممنوع تخترع أو تخمّن أي منهما، وممنوع تستدعيها ببيانات من محادثة تانية."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string", "description": "الاسم كما ذكره العميل"},
                    "phone": {"type": "string", "description": "رقم الهاتف كما كتبه العميل"},
                },
                "required": ["full_name", "phone"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": (
                "ألغِ موعداً محدداً. استدعها **فقط** بعد: (1) استخدام find_my_appointments، "
                "(2) عرض تفاصيل الموعد على العميل، (3) موافقته الصريحة على الإلغاء. "
                "لا تلغي أبداً بمبادرة منك ولا بناءً على تخمين."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": (
                            "انسخ قيمة الحقل `reference` من نتيجة find_my_appointments **حرفياً**، "
                            "حرف بحرف، للموعد اللي وافق العميل على إلغائه. "
                            "ممنوع تكتب قيمة من عندك، وممنوع تستخدم ترتيب الموعد بالقائمة."
                        ),
                    },
                    "full_name": {"type": "string", "description": "نفس الاسم المستخدم بالتحقق"},
                    "phone": {"type": "string", "description": "نفس الرقم المستخدم بالتحقق"},
                    "reason": {"type": "string", "description": "سبب الإلغاء إن ذكره العميل"},
                },
                "required": ["reference", "full_name", "phone"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": (
                "افتح تذكرة تصعيد لفريق العيادة. استخدم emergency لمضاعفات ما بعد الإجراء، "
                "medical للاستفسارات الطبية غير الطارئة، manager للشكاوى، reception لطلبات تعديل المواعيد."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["reception", "manager", "medical", "emergency"],
                    },
                    "reason": {
                        "type": "string",
                        "description": "ملخص واضح للحالة كما وصفها العميل",
                    },
                    "full_name": {
                        "type": "string",
                        "description": (
                            "اسم العميل إذا ذكره بالمحادثة. لا تخمّنه — اتركه فاضي إذا ما ذكره، "
                            "والنظام بيجيبه من بياناته السابقة إن وُجدت."
                        ),
                    },
                    "phone": {
                        "type": "string",
                        "description": (
                            "رقم العميل إذا ذكره. مهم جداً بحالات الطوارئ ليقدر الطبيب "
                            "يتصل فيه فوراً. لا تخترعه."
                        ),
                    },
                },
                "required": ["level", "reason"],
                "additionalProperties": False,
            },
        },
    },
]


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _digits_of(text: str) -> str:
    return "".join(ch for ch in (text or "").translate(_DIGITS) if ch.isdigit())


def _given_in_this_message(phone: str, user_message: str | None) -> bool:
    """
    هل كتب العميل هذا الرقم **بالرسالة الحالية**؟

    حارس صلب ضد إعادة استخدام بيانات من رسائل قديمة. التعليمات وحدها ما نفعت:
    عند طلب «سجّلني على نفس البيانات» الموديل سحب الاسم والرقم من رسالة سابقة
    وسجّلهم بدون إذن. هون بنتحقق من الأرقام نفسها، فما بيقدر يتجاوزها.
    """
    if user_message is None:          # مسارات بدون سياق رسالة (CLI/اختبارات)
        return True
    local = phone[3:] if phone.startswith("962") else phone
    return local.lstrip("0") in _digits_of(user_message)


def _booking_contact_allowed(
    conversation_id: int | None,
    email: str,
    phone: str,
    user_message: str | None,
) -> bool:
    """Allow prior-turn contact only after this conversation verified the same email."""
    if _given_in_this_message(phone, user_message):
        return True
    return bool(
        verification_required() and email and is_verified(conversation_id, email)
    )


def _capture_lead(conversation_id: int | None, args: dict, user_message: str | None = None) -> dict:
    full_name = (args.get("full_name") or "").strip()
    phone_raw = (args.get("phone") or "").strip()
    phone = normalize_jordan_phone(phone_raw)

    if len(full_name) < 3:
        return {"ok": False, "error": "الاسم غير مكتمل — اطلب من العميل اسمه الكامل."}
    if not phone:
        return {
            "ok": False,
            "error": (
                "رقم الهاتف غير صالح. اطلب من العميل رقم موبايل أردني صحيح "
                "بصيغة 07XXXXXXXX واستدعِ الأداة مرة ثانية."
            ),
        }
    if not _given_in_this_message(phone, user_message):
        return {
            "ok": False,
            "error": (
                "هذا الرقم مش مكتوب برسالة العميل الحالية — يبدو إنك أخذته من رسالة سابقة. "
                "**ممنوع تسجّل بيانات تواصل من سجل المحادثة.** اطلب من العميل يكتب اسمه ورقمه "
                "من جديد بهذه الرسالة، وبعدها استدعِ الأداة."
            ),
        }

    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO leads (conversation_id, full_name, phone, service_interest,
                               preferred_time, gender, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                conversation_id,
                full_name,
                phone,
                args.get("service_interest"),
                args.get("preferred_time"),
                args.get("gender", "unknown"),
                args.get("notes"),
            ),
        ).fetchone()

    logger.info("lead #%s مسجّل: %s / %s", row["id"], full_name, phone)
    clinic_phone = get_settings().clinic_phone
    return {
        "ok": True,
        "lead_id": row["id"],
        "phone_saved": format_phone_display(phone),
        "clinic_phone": clinic_phone,
        "message": (
            "تم تسجيل البيانات. اشكر العميل باسمه، وأكّد له أن الاستقبال رح يتواصل معه قريباً "
            "لترتيب موعده — وما تأكدله موعد محدد. "
            f"وأضف بنهاية ردك أنه لو بيفضّل يتصل بنفسه، رقم العيادة هو {clinic_phone}. "
            "اكتب الرقم كما هو حرفياً، وبنفس لغة العميل."
        ),
    }


def _normalize_gender(value: str | None) -> str:
    return value if value in {"male", "female", "unknown"} else "unknown"


def _parse_date(text: str | None) -> Date | None:
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


# أسباب إغلاق اليوم كما بترجعها الجدولة → تعليمة للموديل بدل رمز خام
_CLOSED_REASONS = {
    "past": "هذا التاريخ مضى. اسأل العميل عن يوم قادم.",
    "too_far": "هذا التاريخ أبعد من المدى المتاح للحجز. اقترح عليه يوماً أقرب.",
    "friday_closed": "الجمعة العيادة مغلقة. وضّح ذلك للعميل واقترح يوماً آخر.",
    "fully_booked": "هذا اليوم محجوز بالكامل. أخبر العميل واعرض عليه أقرب يوم فيه شواغر.",
}


# كم يوم بنرجّع أوقاته **كاملة** بوضع «أقرب المتاح»
_DETAIL_DAYS = 5


def _NEXT_STEP_HINT() -> str:
    """
    الخطوة التالية بتنقال بنتيجة الأداة مش بالبرومبت وحده.

    التعليمة موجودة بنتيجة الأداة نفسها حتى يحافظ الموديل على ترتيب التحقق
    وما يطلب بيانات التواصل أكثر من مرة.
    """
    if not verification_required():
        return (
            "\n▶ الخطوة التالية بعد ما يختار وقتاً: اطلب **اسمه الكامل ورقمه برسالة وحدة**، "
            "وبعدها احجز مباشرة."
        )
    return (
        "\n▶ الخطوة التالية بعد ما يختار وقتاً: اطلب **اسمه الكامل ورقمه وإيميله برسالة وحدة**. "
        "استدعِ `send_email_code` فوراً، وبعد ما يتحقق الرمز احجز باستخدام نفس البيانات. "
        "⚠ لا تطلب الاسم أو الرقم أو الإيميل مرة ثانية بعد التحقق."
    )


def _next_days_detail(
    gender: str, service: str | None = None, doctor_id: str | None = None
) -> list[dict]:
    """
    أقرب أيام فيها شواغر، وكل يوم بكامل أوقاته — باستعلام واحد.

    السبب اللي خلّانا نرجع كل الأوقات بدل عيّنة: العيّنة (وقتين باليوم) كانت
    بتخلّي الموديل يقول «هذا الوقت مش متاح» لوقت متاح فعلاً، لأن التعليمات
    بتمنعه يذكر أي وقت برّا نتيجة الأداة. العيّنة الناقصة + المنع = رفض كاذب.
    """
    raw = next_available_slots(
        gender, limit=240, days_ahead=14, per_day=48,
        lead_minutes=OFFER_LEAD_MINUTES, service=service,
        doctor_id=doctor_id,
    )
    grouped: dict[str, list[str]] = {}
    for slot in raw:
        grouped.setdefault(slot["date"], []).append(slot["time"])
    return [{"date": day, "slots": grouped[day]} for day in sorted(grouped)[:_DETAIL_DAYS]]


def _check_availability(conversation_id: int | None, args: dict) -> dict:
    """
    مصدر الأوقات الوحيد المسموح للموديل.

    بديل نموذج الحجز: قبل هيك كان التقويم بالواجهة هو اللي بيعرض الشواغر،
    وكان ممنوع على الموديل يقترح أوقات. هلأ الحجز صار بالشات كامل، فلازم
    يظل في مصدر واحد للأوقات — هالأداة — بدل ما يخمّن الموديل من عنده.
    """
    gender = _normalize_gender(args.get("gender"))
    raw_date = (args.get("date") or "").strip()

    # الخانة بتستوعب خدمات مختلفة بنفس الوقت، فالتوفر بيعتمد على الخدمة.
    # بدون خدمة بنعرض كل أوقات الدوام — وهاد صحيح لأن الوقت شبه أكيد متاح
    # لخدمة ما، بس بنطلب من الموديل يسأل عن الخدمة عشان الجواب يكون دقيق.
    requested_service = get_service(args.get("service"))
    service_id = requested_service.id if requested_service else None
    requested_doctor = get_doctor(args.get("doctor_id"))
    doctor_id = requested_doctor.id if requested_doctor else None
    if args.get("doctor_id") and requested_doctor is None:
        return {"ok": False, "error": "الطبيب المطلوب غير موجود ضمن قائمة أطباء العيادة الحالية."}
    if doctor_id and not service_id:
        return {"ok": False, "error": "حدّد الخدمة أولاً حتى نتحقق إن الطبيب يقدمها."}
    if doctor_id and not doctor_can_do_service(doctor_id, service_id):
        return {
            "ok": False,
            "error": (
                f"{requested_doctor.name} غير مخصص لخدمة {service_id}. "
                "وضّح ذلك للعميل واعرض طبيباً مناسباً أو استشارة فقط."
            ),
        }

    if not raw_date:
        days = _next_days_detail(gender, service_id, doctor_id)
        if not days:
            return {
                "ok": True,
                "days": [],
                "slots": [],
                "message": (
                    "ما في شواغر بالأيام القريبة. اعتذر للعميل واعرض عليه الاتصال بالاستقبال "
                    f"على {get_settings().clinic_phone} ليرتبوا له موعداً."
                ),
            }
        suggest = [{"date": d["date"], "time": t} for d in days[:3] for t in d["slots"][:2]][:4]
        return {
            "ok": True,
            "mode": "next_available",
            "days": days,
            "slots": suggest,
            "message": (
                "`days` فيه **كل** الأوقات المتاحة فعلياً لأقرب أيام فيها شواغر — مش عيّنة. "
                "ابدأ باقتراح ٣–٤ أوقات من `slots` بصيغة مقروءة بلغة العميل واسأله أيها يناسبه. "
                "⚠ بس إذا سأل عن يوم أو وقت محدد، **دوّر عليه بـ `days` أول** قبل ما تجاوب: "
                "لو اليوم موجود بـ `days` فقائمة أوقاته كاملة هناك، ولو مش موجود استدعِ "
                "`check_availability` بتاريخ ذاك اليوم. "
                "🔒 ممنوع تقول إن وقت «مش متاح» إلا بعد ما تتأكد منه بقائمة أوقات ذاك اليوم بالذات. "
                "الأوقات بنظام ٢٤ ساعة — حوّلها لصيغة مقروءة بالعرض، بس احتفظ فيها كما هي للحجز."
                + _NEXT_STEP_HINT()
            ),
        }

    day = _parse_date(raw_date)
    if day is None:
        return {"ok": False, "error": "صيغة التاريخ غير صحيحة — استخدم YYYY-MM-DD."}

    # هامش أوسع بالعرض حتى الخانة تضل قابلة للحجز لما يرد العميل بعد رسالة أو اتنين
    availability = get_availability(
        day, gender, lead_minutes=OFFER_LEAD_MINUTES, service=service_id,
        doctor_id=doctor_id,
    )
    if not availability.slots:
        reason = availability.reason or "fully_booked"
        return {
            "ok": True,
            "date": day.isoformat(),
            "slots": [],
            "reason": reason,
            "message": (
                _CLOSED_REASONS.get(reason, "ما في أوقات متاحة بهذا اليوم.")
                + " استدعِ check_availability بدون تاريخ عشان تعرض عليه أقرب البدائل."
            ),
        }

    return {
        "ok": True,
        "date": day.isoformat(),
        "slots": availability.slots,
        "message": (
            "هذه **كل** الأوقات المتاحة فعلياً بهذا اليوم. "
            "إذا كان العميل طلب وقتاً معيناً: إذا هو بالقائمة أكّدله إنه متاح، "
            "وإذا مش بالقائمة قلّه إنه محجوز واقترح أقرب وقت إله منها. "
            "وإذا ما طلب وقتاً محدداً اعرض ٤–٥ أوقات موزّعة على اليوم واسأله أيها يناسبه. "
            "🔒 ممنوع تذكر أي وقت مش موجود بالقائمة. "
            "الأوقات بنظام ٢٤ ساعة — حوّلها لصيغة مقروءة بالعرض، بس احتفظ فيها كما هي للحجز."
            + _NEXT_STEP_HINT()
        ),
    }


# رسائل رفض الحجز — كل سبب برسالته، عشان الموديل يعرف شو يقول للعميل
_BOOKING_ERRORS = {
    "service_taken": (
        "هذه الخدمة محجوزة بهذا الوقت (خدمة وحدة لكل خانة). "
        "استدعِ check_availability بنفس الخدمة واعرض عليه أقرب البدائل."
    ),
    "already_booked_this_slot": (
        "العميل عنده أصلاً موعد بنفس التاريخ والوقت. "
        "ما بيقدر يكون بمكانين بنفس اللحظة — اعرض عليه وقتاً ثانياً."
    ),
    "too_many_active": (
        "العميل وصل الحد الأقصى ({active} من {limit}) للمواعيد القادمة. "
        "وضّحله بلطف إنه لازم يكمّل أو يلغي موعداً قبل ما يحجز جديد، "
        "واعرض عليه التواصل مع الاستقبال إذا بدّه استثناء."
    ),
    "rate_limited": (
        "محاولات حجز كثيرة من نفس الرقم خلال ساعة ({recent} من {limit}). "
        "اطلب منه يستنى شوي أو يتواصل مع الاستقبال مباشرة."
    ),
}


def _send_email_code(conversation_id: int | None, args: dict, user_message: str | None = None) -> dict:
    """بيبعت رمز التحقق. الإيميل لازم يكون مكتوباً برسالة العميل الحالية."""
    email = normalize_email(args.get("email") or "")

    if not is_valid_email(email):
        return {"ok": False, "error": "صيغة الإيميل غير صحيحة — اطلب من العميل يكتبه من جديد."}
    if user_message is not None and email not in (user_message or "").lower():
        return {
            "ok": False,
            "error": (
                "هذا الإيميل مش مكتوب برسالة العميل الحالية. "
                "**ممنوع تاخد بيانات تواصل من رسالة سابقة** — اطلب منه يكتب إيميله بهاي الرسالة."
            ),
        }
    if not verification_required():
        return {
            "ok": True,
            "skipped": True,
            "message": "التحقق بالبريد معطّل حالياً على السيرفر — كمّل الحجز بدون رمز.",
        }

    result = issue_code(conversation_id, email, "ar")
    if not result["ok"]:
        return {"ok": False, "error": _CODE_ERRORS.get(
            result["error"], "تعذّر إرسال رمز التحقق. اعرض على العميل التواصل مع الاستقبال."
        )}

    return {
        "ok": True,
        "email": email,
        "message": (
            f"انبعت رمز تحقق من ٦ أرقام على {email}. "
            "اطلب من العميل يكتبلك الرمز، وقلّه يتفقّد مجلد الرسائل غير المرغوب فيها إذا ما وصله. "
            f"الرمز صالح {result['ttl_minutes']} دقيقة. "
            "🔒 ممنوع تحجز قبل ما تتحقق من الرمز بـ `verify_email_code`."
        ),
    }


_CODE_ERRORS = {
    "rate_limited": (
        "انبعتت رموز كثيرة على هذا الإيميل خلال ساعة. "
        "اطلب من العميل يستنى شوي أو يتواصل مع الاستقبال."
    ),
    "send_failed": (
        "تعذّر إرسال الإيميل. اعتذر للعميل واعرض عليه التواصل مع الاستقبال لتثبيت الموعد."
    ),
    "smtp_not_configured": "التحقق بالبريد مش مهيأ على السيرفر — كمّل بدون رمز.",
}

_VERIFY_ERRORS = {
    "no_code": "ما في رمز مرسل لهذا الإيميل. استدعِ `send_email_code` أول.",
    "expired": "الرمز انتهت صلاحيته. استدعِ `send_email_code` عشان تبعتله رمزاً جديداً.",
    "too_many_attempts": (
        "محاولات خاطئة كثيرة. استدعِ `send_email_code` لإرسال رمز جديد."
    ),
}


def _verify_email_code(conversation_id: int | None, args: dict) -> dict:
    email = normalize_email(args.get("email") or "")
    code = (args.get("code") or "").strip()

    if not is_valid_email(email):
        return {"ok": False, "error": "صيغة الإيميل غير صحيحة."}
    if not code:
        return {"ok": False, "error": "اطلب من العميل الرمز المكوّن من ٦ أرقام."}

    result = check_code(conversation_id, email, code)
    if result["ok"]:
        return {
            "ok": True,
            "email": email,
            "message": (
                "تم التحقق من الإيميل. كمّل الحجز بـ `book_appointment` "
                "ومرّر نفس الإيميل بالحقل `email`."
            ),
        }

    if result["error"] == "wrong_code":
        left = result.get("attempts_left", 0)
        return {
            "ok": False,
            "error": (
                f"الرمز غير صحيح. باقي {left} محاولة. "
                "اطلب من العميل يتأكد من الرمز اللي وصله ويكتبه من جديد."
                if left else
                "الرمز غير صحيح وخلصت المحاولات. استدعِ `send_email_code` لرمز جديد."
            ),
        }
    return {"ok": False, "error": _VERIFY_ERRORS.get(result["error"], "تعذّر التحقق من الرمز.")}


def _book_appointment(conversation_id: int | None, args: dict, user_message: str | None = None) -> dict:
    """يسجّل طلب موعد بحالة requested — نفس ما كان يعمل نموذج الحجز، بس من داخل الشات."""
    full_name = (args.get("full_name") or "").strip()
    phone = normalize_jordan_phone((args.get("phone") or "").strip())
    email = normalize_email(args.get("email") or "")
    gender = _normalize_gender(args.get("gender"))

    if len(full_name) < 3:
        return {"ok": False, "error": "الاسم غير مكتمل — اطلب من العميل اسمه الكامل."}
    if not phone:
        return {
            "ok": False,
            "error": (
                "رقم الهاتف غير صالح. اطلب من العميل رقم موبايل أردني صحيح "
                "بصيغة 07XXXXXXXX واستدعِ الأداة مرة ثانية."
            ),
        }
    if not _booking_contact_allowed(conversation_id, email, phone, user_message):
        return {
            "ok": False,
            "error": (
                "هذا الرقم مش مكتوب برسالة العميل الحالية. "
                "استخدم بيانات رسالة سابقة فقط إذا تم التحقق من إيميل العميل بنجاح بنفس المحادثة."
            ),
        }

    day = _parse_date(args.get("date"))
    if day is None:
        return {"ok": False, "error": "صيغة التاريخ غير صحيحة — استخدم YYYY-MM-DD."}

    time_text = (args.get("time") or "").strip()
    try:
        slot = datetime.strptime(time_text, "%H:%M").time()
    except ValueError:
        return {"ok": False, "error": "صيغة الوقت غير صحيحة — استخدم HH:MM بنظام ٢٤ ساعة."}

    # الخدمة إلزامية: النموذج القديم كان بيفرضها بقائمة منسدلة، ولما صار الحجز
    # بالشات صار الموديل يحجز بدونها وبتوصل الاستقبال مواعيد بخانة خدمة فاضية.
    # الحارس هون مش بالسكيمة وحدها لأن الموديل بيقدر يبعت قيمة برّا الكتالوج.
    # ولازم تنحدّد **قبل** فحص التوفر، لأن التوفر صار يعتمد عليها.
    service = get_service(args.get("service"))
    if service is None:
        return {
            "ok": False,
            "error": (
                "ما حددت خدمة صالحة. **اسأل العميل شو الخدمة اللي بدّه ياها** قبل ما تحجز — "
                "ممنوع تحجز بدون خدمة وممنوع تخمّنها. "
                "إذا قال إنه مش متأكد أو بدّه يشوف الطبيب أول، استخدم `not_sure`."
            ),
        }

    requested_doctor_id = (args.get("doctor_id") or "").strip() or None
    requested_doctor = get_doctor(requested_doctor_id)
    if requested_doctor_id and requested_doctor is None:
        return {"ok": False, "error": "الطبيب المطلوب غير موجود ضمن قائمة أطباء العيادة الحالية."}
    if requested_doctor_id and not doctor_can_do_service(requested_doctor_id, service.id):
        return {
            "ok": False,
            "error": (
                f"{requested_doctor.name} لا يقدم خدمة {service.en}. "
                "اعرض على العميل طبيباً مناسباً، أو اسمح بالطبيب المطلوب إذا اختار استشارة فقط."
            ),
        }
    doctor = assigned_doctor(service.id, requested_doctor_id)

    # التحقق من البريد — الحاجز الأساسي ضد الحجز العشوائي
    if verification_required():
        if not email:
            return {
                "ok": False,
                "error": (
                    "ناقص إيميل العميل. اطلب منه إيميله، بعدها استدعِ `send_email_code` "
                    "ليوصله رمز تحقق، وبعد ما يعطيك الرمز استدعِ `verify_email_code`، "
                    "وبس بعدها احجز."
                ),
            }
        if not is_valid_email(email):
            return {"ok": False, "error": "صيغة الإيميل غير صحيحة — اطلب من العميل يكتبه من جديد."}
        if not is_verified(conversation_id, email):
            return {
                "ok": False,
                "error": (
                    f"إيميل {email} لسا ما تحقّقنا منه. استدعِ `send_email_code` أول، "
                    "واطلب من العميل الرمز اللي وصله، وتحقّق منه بـ `verify_email_code` "
                    "قبل ما تحجز. **ممنوع تقول إن الموعد انسجّل قبل ما يتم التحقق.**"
                ),
            }

    # إعادة التحقق من التوفر لحظة الحجز: بين ما عرضنا الأوقات وبين ما اختار العميل
    # ممكن تكون الخانة انحجزت، وممكن يكون الموديل اخترع وقتاً مش من القائمة.
    # التوفر بيتحسب لهذه الخدمة تحديداً — نفس الوقت ممكن يكون متاحاً لخدمة تانية.
    availability = get_availability(
        day, gender, service=service.id, phone=phone, email=email or None,
        doctor_id=doctor.id if doctor else None,
    )
    if time_text not in availability.slots:
        return {
            "ok": False,
            "error": (
                f"الوقت {time_text} بتاريخ {day.isoformat()} مش متاح لخدمة {service.id}. "
                "اعتذر للعميل واعرض عليه الأوقات المتاحة أدناه ليختار منها."
            ),
            "available_slots": availability.slots,
        }

    result = create_appointment(
        full_name=full_name,
        phone=phone,
        day=day,
        slot=slot,
        service=service.id,
        gender=gender,
        notes=args.get("notes"),
        conversation_id=conversation_id,
        email=email or None,
        doctor_id=doctor.id if doctor else None,
    )
    if not result["ok"]:
        return {"ok": False, "error": _BOOKING_ERRORS.get(
            result["error"],
            "ما قدرنا نسجّل الطلب. استدعِ check_availability واعرض عليه البدائل.",
        ).format(**result)}

    logger.info("موعد #%s تم طلبه من الشات: %s / %s", result["appointment_id"], full_name, phone)

    # الرسالة تُنشأ بالصادر فقط؛ عامل sms-worker يرسلها بدون ما يعلّق رد الشات.
    from .notifications import create_appointment_notification

    notice = create_appointment_notification(result["appointment_id"], "appointment_requested")
    if notice:
        result["notification_id"] = notice["notification_id"]

    result["ui_action"] = "appointment_requested"
    result["service_label"] = service_label(service.id, "ar")
    result["doctor_id"] = doctor.id if doctor else None
    result["doctor_name"] = doctor.name if doctor else None
    result["phone_saved"] = format_phone_display(phone)
    result["message"] = (
        "تم تسجيل **طلب** الموعد بنجاح. أكّد للعميل التاريخ والوقت اللي انسجّلوا بصيغة مقروءة بلغته، "
        "ووضّحله إن هذا طلب موعد مش موعد مؤكد، وإنه رح توصله **رسالة نصية** على رقمه أول ما يتأكد. "
        "ممنوع تقول «تم حجزك» أو «موعدك مثبّت» أو «بنشوفك يوم كذا»، "
        "وممنوع تقول إن حدا رح يتصل فيه لتأكيد الموعد."
    )
    return result


def _send_location(conversation_id: int | None, args: dict, turn_tools: set[str] | None = None) -> dict:
    """بيرجّع بيانات الموقع للواجهة عشان تعرضها كبطاقة. ما بيخترع عنوان أبداً."""
    settings = get_settings()

    if not location_configured():
        return {
            "ok": False,
            "error": (
                "عنوان العيادة مش متوفر عندك. **لا تخترع أي عنوان أو اسم شارع أو رقم طابق.** "
                f"اعتذر بلطف واعرض على العميل الاتصال بالاستقبال على {settings.clinic_phone} "
                "ليدلّوه على الموقع بالضبط."
            ),
        }

    # بطاقة الموقع بتنعرض بالواجهة بكل الأحوال. اللي بيتغيّر هو التعليمة للموديل:
    # لما يكون بنفس الدور حجز أو إلغاء، التعليمات وحدها ما نفعت — الموديل كان
    # يكتب العنوان **بدل** تأكيد الموعد، فالعميل ما بيعرف إذا انحجزله شي.
    # الحل إننا نشيل التعليمة المتضاربة أصلاً بدل ما نضيف تحذير أقوى فوقها.
    payload = {
        "ok": True,
        "ui_action": "show_location",
        "address_ar": describe_location("ar"),
        "address_en": describe_location("en"),
        "maps_url": settings.clinic_maps_url,
    }

    # لما يكون بنفس الدور حجز أو إلغاء، بنرجّع بيانات البطاقة **بدون أي تعليمة**.
    # جرّبنا تعليمات متدرّجة الشدة («الموقع إضافة»، «لا تكتب العنوان») وكلها فشلت:
    # الموديل كان يكتب العنوان ويهمل تأكيد الموعد، فالعميل ما بيعرف إذا انحجزله شي.
    # أي نص هون بيتنافس مع تعليمة الحجز، فالحل إنه ما يكون في نص أصلاً —
    # البطاقة بتنعرض بالواجهة، والرد بيضل لتأكيد الموعد وحده.
    if turn_tools and turn_tools & {"book_appointment", "cancel_appointment"}:
        return payload

    payload["message"] = (
        "انعرضت بطاقة الموقع قدام العميل. اذكر بجملة قصيرة الشارع والمبنى والطابق بلغته، "
        "وقلّه إنه يقدر يفتح الموقع على الخرائط من البطاقة. لا تضيف أي تفصيل غير موجود بالبطاقة."
    )
    return payload


def _find_my_appointments(conversation_id: int | None, args: dict) -> dict:
    full_name = (args.get("full_name") or "").strip()
    phone = normalize_jordan_phone((args.get("phone") or "").strip())

    if len(full_name) < 3:
        return {"ok": False, "error": "اطلب من العميل اسمه الكامل كما حجز فيه."}
    if not phone:
        return {"ok": False, "error": "رقم الهاتف غير صالح. اطلب رقم أردني بصيغة 07XXXXXXXX."}

    found = find_appointments(phone, full_name)
    if not found:
        logger.info("بحث عن مواعيد بدون نتيجة (تحقق فاشل أو ما في مواعيد)")
        return {
            "ok": True,
            "appointments": [],
            "message": (
                "ما لقينا مواعيد قادمة بهالاسم والرقم. اعتذر بلطف، اطلب منه يتأكد من الرقم "
                "والاسم اللي حجز فيهم، واعرض عليه تحويله للاستقبال إذا ضل نفس النتيجة. "
                "لا تجزم إنه ما عنده موعد نهائياً."
            ),
        }

    for appointment in found:
        appointment["service_label"] = service_label(appointment.get("service"), "ar")

    return {
        "ok": True,
        "appointments": found,
        "message": (
            "اعرض المواعيد على العميل (التاريخ والوقت والخدمة) واسأله يأكدلك أي واحد بدو يلغي. "
            "لا تلغي شي قبل موافقته الصريحة."
        ),
    }


def _cancel_appointment(conversation_id: int | None, args: dict) -> dict:
    full_name = (args.get("full_name") or "").strip()
    phone = normalize_jordan_phone((args.get("phone") or "").strip())

    result = resolve_and_cancel(
        full_name=full_name,
        phone_raw=args.get("phone", ""),
        reference=args.get("reference"),
        reason=args.get("reason"),
        by="chat",
    )

    if not result["ok"]:
        messages = {
            "invalid_name": "اطلب من العميل اسمه الكامل كما حجز فيه.",
            "invalid_phone": "رقم الهاتف غير صالح. اطلب رقم أردني بصيغة 07XXXXXXXX.",
            "no_appointments": "ما في مواعيد قادمة بهالاسم والرقم. تأكد من البيانات مع العميل.",
            "not_found": "معرّف الموعد غير موجود. شغّل find_my_appointments وانسخ reference حرفياً.",
            "verification_failed": (
                "هذا المعرّف بيخص موعد شخص تاني. **ممنوع** تلغيه. "
                "شغّل find_my_appointments مرة تانية وانسخ قيمة reference حرفياً."
            ),
            "already_cancelled": "هذا الموعد ملغي أصلاً. طمّن العميل إنه ما في موعد قائم.",
            "already_completed": "هذا الموعد تم تنفيذه ومش قابل للإلغاء.",
            "already_no_show": "هذا الموعد مسجّل كعدم حضور.",
            "already_passed": "هذا الموعد وقته مضى ومش قابل للإلغاء.",
        }
        if result["error"] == "ambiguous":
            listing = "، ".join(
                f"{c['reference']} ({c['date']} {c['time']})" for c in result["candidates"]
            )
            return {"ok": False, "error": f"العميل عنده أكثر من موعد: {listing}. اسأله أي واحد بدو يلغي."}
        logger.warning("فشل الإلغاء من الشات: %s", result["error"])
        return {"ok": False, "error": messages.get(result["error"], result["error"])}

    logger.info("موعد %s تم إلغاؤه من الشات", result["reference"])

    # رسالة الإلغاء تُنشأ بالصادر فقط. عامل sms-worker يرسلها بدون ما يعلّق رد الشات.
    from .notifications import create_appointment_notification
    from .scheduling import parse_reference

    appointment_id = parse_reference(result["reference"])
    notice = create_appointment_notification(appointment_id, "patient_cancelled")
    if notice:
        result["notification_id"] = notice["notification_id"]

    # سياسة العيادة: الإلغاء قبل 24 ساعة. الإلغاء المتأخر بينبّه الاستقبال فوراً.
    if result["late_cancellation"]:
        _escalate(
            conversation_id,
            {
                "level": "reception",
                "reason": (
                    f"إلغاء متأخر (أقل من 24 ساعة) للموعد {result['reference']} "
                    f"بتاريخ {result['date']} الساعة {result['time']} — {full_name}"
                ),
            },
        )
        result["message"] = (
            "تم الإلغاء. نبّه العميل بلطف إن سياسة العيادة تفضّل الإلغاء قبل 24 ساعة، "
            "وإن الاستقبال تم إشعاره. واعرض عليه حجز موعد بديل — استدعِ check_availability "
            "وأعطه أقرب الأوقات المتاحة."
        )
    else:
        result["message"] = (
            "تم الإلغاء بنجاح. أكّد للعميل بوضوح إن موعده انلغى، "
            "واعرض عليه حجز موعد بديل إذا بدو — استدعِ check_availability "
            "وأعطه أقرب الأوقات المتاحة."
        )
    result["ui_action"] = "appointment_cancelled"
    return result


def _known_contact(conversation_id: int | None) -> tuple[str | None, str | None]:
    """
    آخر اسم/رقم عرفناه بهذه المحادثة — من تسجيل عميل أو حجز موعد.
    بيخلّي تصعيد الطوارئ يحمل رقماً حتى لو المريض ما أعطاه بنفس الرسالة.
    """
    if conversation_id is None:
        return None, None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT full_name, phone FROM (
                SELECT full_name, phone, created_at FROM leads        WHERE conversation_id = %s
                UNION ALL
                SELECT full_name, phone, created_at FROM appointments WHERE conversation_id = %s
            ) known
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id, conversation_id),
        ).fetchone()
    return (row["full_name"], row["phone"]) if row else (None, None)


def _escalate(conversation_id: int | None, args: dict) -> dict:
    level = args.get("level", "reception")
    reason = (args.get("reason") or "").strip() or "غير محدد"

    full_name = (args.get("full_name") or "").strip() or None
    phone = normalize_jordan_phone((args.get("phone") or "").strip())

    # استخراج بيانات التواصل من سجل المحادثة **مقصور على الطوارئ**.
    # المبرر: بحالة طارئة تأخير الوصول للمريض خطر على حياته، فبنقبل استخدام
    # بيانات أعطاها سابقاً. بأي حالة تانية (حجز، استفسار) بنطلبها من جديد
    # بدل ما نعيد استخدامها بصمت — وهاد يطابق بند 38 بوثيقة جورمول.
    if level == "emergency" and (not full_name or not phone):
        known_name, known_phone = _known_contact(conversation_id)
        full_name = full_name or known_name
        phone = phone or known_phone

    # حادثة واحدة = صف واحد. الموديل بيستدعي الأداة أكثر من مرة (تكرار بنفس الدور،
    # أو متابعة لما يعطينا العميل رقمه) — بنغني الصف الموجود بدل ما نغرق اللوحة
    # بتصعيدات مكررة، وهاد أخطر شي بحالات الطوارئ.
    with get_conn() as conn, conn.transaction():
        existing = None
        if conversation_id is not None:
            existing = conn.execute(
                """
                SELECT id, full_name, phone FROM escalations
                WHERE conversation_id = %s AND level = %s AND handled = false
                  AND created_at > now() - interval '30 minutes'
                ORDER BY created_at DESC LIMIT 1
                FOR UPDATE
                """,
                (conversation_id, level),
            ).fetchone()

        if existing:
            row = conn.execute(
                """
                UPDATE escalations
                SET full_name = COALESCE(%s, full_name),
                    phone     = COALESCE(%s, phone),
                    reason    = %s
                WHERE id = %s
                RETURNING id
                """,
                (full_name, phone, reason, existing["id"]),
            ).fetchone()
            logger.info("تصعيد #%s تم تحديثه بدل تكراره", row["id"])
        else:
            row = conn.execute(
                """
                INSERT INTO escalations (conversation_id, level, reason, full_name, phone)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (conversation_id, level, reason, full_name, phone),
            ).fetchone()

    logger.warning("escalation #%s [%s]: %s", row["id"], level, reason)

    if level == "emergency":
        settings = get_settings()
        guidance = (
            f"حالة طارئة. وجّه العميل فوراً للاتصال بموبايل العيادة للتواصل العاجل {settings.emergency_phone}، "
            "وأخبره إنه لو ما في رد يتوجه لأقرب مستشفى أو طوارئ بدون انتظار. "
            "المعلومتين إلزاميتين، و**بلغة العميل نفسها** (رسالة إنجليزية ← رد إنجليزي). "
            "لا تعطِ أي نصيحة طبية، ولا تعطِ رقم الحجز العادي."
        )
        if not phone:
            # بدون رقم ما بيقدر الطبيب يتابع الحالة — بنطلبه بعد تعليمات السلامة
            guidance += (
                " ⚠ ما عنا رقم تواصل لهذا العميل. **بعد** ما تعطيه تعليمات السلامة أعلاه "
                "(مش قبلها ولا بدالها)، اطلب منه اسمه ورقمه بجملة قصيرة ليقدر الطبيب "
                "يتابع حالته، وفور ما يعطيك إياهم استدعِ escalate مرة تانية بنفس المستوى "
                "مع الاسم والرقم. لا تؤخّر تعليمات الطوارئ لأي سبب."
            )
    elif level == "medical":
        guidance = "تم تحويل الاستفسار للطبيب المسؤول. أخبر العميل أن الطبيب سيتواصل معه."
    elif level == "manager":
        guidance = "تم تسجيل الشكوى لمدير العيادة. اعتذر بصدق وأخبره أن المدير سيتواصل معه."
    else:
        guidance = "تم تحويل الطلب لمكتب الاستقبال."

    return {"ok": True, "escalation_id": row["id"], "level": level, "message": guidance}


_HANDLERS = {
    "capture_lead": _capture_lead,
    "check_availability": _check_availability,
    "send_email_code": _send_email_code,
    "verify_email_code": _verify_email_code,
    "book_appointment": _book_appointment,
    "send_location": _send_location,
    "find_my_appointments": _find_my_appointments,
    "cancel_appointment": _cancel_appointment,
    "escalate": _escalate,
}

# أدوات بتسجّل بيانات تواصل → لازم تشوف نص رسالة العميل الحالية للتحقق منها
_NEEDS_USER_MESSAGE = {"capture_lead", "book_appointment", "send_email_code"}

# أدوات بتتغيّر تعليمتها حسب شو انستدعى قبلها بنفس الدور
_NEEDS_TURN_CONTEXT = {"send_location"}


def execute_tool(
    name: str,
    raw_arguments: str,
    conversation_id: int | None,
    user_message: str | None = None,
    turn_tools: set[str] | None = None,
) -> dict:
    """
    ينفّذ استدعاء أداة قادم من الموديل ويرجّع نتيجة JSON-safe.

    `turn_tools` = أسماء الأدوات اللي نجحت بنفس دور المحادثة قبل هاي —
    بتخلّي الأداة تعرف سياقها وتتجنّب تعليمة بتتضارب مع أداة قبلها.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": f"أداة غير معروفة: {name}"}
    try:
        args = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "صيغة المعطيات غير صالحة، أعد المحاولة."}

    try:
        # أدوات التسجيل بتحتاج نص الرسالة للتحقق إن البيانات مكتوبة فيها
        if name in _NEEDS_USER_MESSAGE:
            return handler(conversation_id, args, user_message)
        if name in _NEEDS_TURN_CONTEXT:
            return handler(conversation_id, args, turn_tools or set())
        return handler(conversation_id, args)
    except Exception as exc:  # pragma: no cover
        logger.exception("فشل تنفيذ الأداة %s", name)
        return {"ok": False, "error": f"خطأ داخلي: {exc}"}
