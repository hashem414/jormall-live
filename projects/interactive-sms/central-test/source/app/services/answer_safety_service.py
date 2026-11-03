from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings


OLD_UNAVAILABLE_MESSAGES = (
    "The JorMall assistant is temporarily unavailable. Please try again later.",
    "The JorMall assistant is temporarily unavailable. Please try again later",
    "مساعد JorMall غير متاح مؤقتًا. يرجى المحاولة مرة أخرى لاحقًا.",
    "مساعد JorMall غير متاح مؤقتًا. يرجى المحاولة مرة أخرى لاحقًا",
)


@dataclass(frozen=True, slots=True)
class PricingIntent:
    category: str
    language: str


def contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def answer_language(text: str) -> str:
    return "ar" if contains_arabic(text) else "en"


def normalized_text(text: str) -> str:
    lowered = (text or "").casefold()
    lowered = lowered.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    lowered = lowered.replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", lowered).strip()


GREETING_PREFIX_PATTERN_EN = re.compile(
    r"^\s*(hello\s+there|hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|greetings|how\s+are\s+you)\b[\s,!.?:-]*(.*)$",
    flags=re.IGNORECASE,
)
GREETING_PREFIX_PATTERN_AR = re.compile(
    r"^\s*(\u0627\u0644\u0633\u0644\u0627\u0645\s+\u0639\u0644\u064a\u0643\u0645(?:\s+\u0648\u0631\u062d\u0645\u0629\s+\u0627\u0644\u0644\u0647)?|\u0645\u0631\u062d\u0628\u0627|\u0645\u0631\u062d\u0628\u0627\u064b|\u0627\u0647\u0644\u0627|\u0623\u0647\u0644\u0627|\u0647\u0644\u0627|\u0633\u0644\u0627\u0645|\u0635\u0628\u0627\u062d\s+\u0627\u0644\u062e\u064a\u0631|\u0645\u0633\u0627\u0621\s+\u0627\u0644\u062e\u064a\u0631|\u0643\u064a\u0641\u0643|\u0643\u064a\u0641\s+\u062d\u0627\u0644\u0643)[\s\u060c\u061b\u061f,!.:-]*(.*)$",
    flags=re.IGNORECASE,
)
GREETING_EMOJI_EDGE_PATTERN = re.compile(
    r"^[\s\U0001F44B\U0001F642\U0001F60A\U0001F600]+|[\s\U0001F44B\U0001F642\U0001F60A\U0001F600]+$"
)


def clean_greeting_remainder(value: str) -> str:
    cleaned = re.sub(r"^[\s,!.?:\-;\u060c\u061b\u061f]+", "", value or "")
    return GREETING_EMOJI_EDGE_PATTERN.sub("", cleaned).strip()


def normalize_greeting_input(value: str) -> str:
    text = GREETING_EMOJI_EDGE_PATTERN.sub("", value or "").strip()
    return re.sub(r"[\u064B-\u065F\u0670]", "", text)


def split_leading_greeting(question: str) -> tuple[str, str, str] | None:
    text = normalize_greeting_input(question)
    if not text:
        return None

    arabic_match = GREETING_PREFIX_PATTERN_AR.match(text)
    if arabic_match:
        greeting = re.sub(r"\s+", " ", arabic_match.group(1)).strip()
        remainder = clean_greeting_remainder(arabic_match.group(2))
        prefix = (
            "\u0648\u0639\u0644\u064a\u0643\u0645 \u0627\u0644\u0633\u0644\u0627\u0645! "
            if "\u0627\u0644\u0633\u0644\u0627\u0645" in greeting
            else "\u0645\u0631\u062d\u0628\u0627\u064b! "
        )
        return "ar", prefix, remainder

    english_match = GREETING_PREFIX_PATTERN_EN.match(text)
    if english_match:
        return "en", "Hello! ", clean_greeting_remainder(english_match.group(2))

    return None


def greeting_only_answer(question: str) -> str | None:
    greeting = split_leading_greeting(question)
    if greeting is None:
        return None
    language, prefix, remainder = greeting
    normalized_remainder = re.sub(
        r"[\s,!.?:;\-\u060c\u061b\u061f]+",
        " ",
        remainder,
    ).strip().casefold()
    conversational_fillers = {
        "how are you",
        "how are you okay",
        "how are you ok",
        "okay",
        "ok",
        "كيف حالك",
        "كيفك",
        "شو اخبارك",
        "شو أخبارك",
    }
    if remainder and normalized_remainder not in conversational_fillers:
        return None
    if language == "ar":
        if prefix.startswith("\u0648\u0639\u0644\u064a\u0643\u0645"):
            return "\u0648\u0639\u0644\u064a\u0643\u0645 \u0627\u0644\u0633\u0644\u0627\u0645 \u0648\u0631\u062d\u0645\u0629 \u0627\u0644\u0644\u0647 \u0648\u0628\u0631\u0643\u0627\u062a\u0647! \u0623\u0647\u0644\u0627\u064b \u0648\u0633\u0647\u0644\u0627\u064b \u0628\u0643 \u0641\u064a JorMall. \u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0646\u064a \u0645\u0633\u0627\u0639\u062f\u062a\u0643 \u0627\u0644\u064a\u0648\u0645\u061f"
        return "\u0645\u0631\u062d\u0628\u0627\u064b! \u0623\u0647\u0644\u0627\u064b \u0648\u0633\u0647\u0644\u0627\u064b \u0628\u0643 \u0641\u064a JorMall. \u0643\u064a\u0641 \u064a\u0645\u0643\u0646\u0646\u064a \u0645\u0633\u0627\u0639\u062f\u062a\u0643 \u0627\u0644\u064a\u0648\u0645\u061f"
    return "Hello! Welcome to JorMall. How can I help you today?"


def prefix_answer_for_leading_greeting(question: str, answer: str) -> str:
    greeting = split_leading_greeting(question)
    if greeting is None:
        return answer
    _, prefix, remainder = greeting
    if not remainder or answer.startswith(prefix):
        return answer
    return f"{prefix}{answer}"


def has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def chatbot_setup_price_text_en() -> str:
    return f"JOD {settings.chatbot_setup_price_jod} plus applicable sales tax"


def chatbot_setup_price_text_ar() -> str:
    return f"{settings.chatbot_setup_price_jod} دينار أردني بالإضافة إلى ضريبة المبيعات المطبقة"


def chatbot_hosting_packages_text_en() -> str:
    return (
        f"1 month: JOD {settings.chatbot_hosting_1_month_jod}; "
        f"3 months: JOD {settings.chatbot_hosting_3_months_jod}; "
        f"6 months: JOD {settings.chatbot_hosting_6_months_jod}; "
        f"12 months: JOD {settings.chatbot_hosting_12_months_jod}, "
        "with sales tax applying to all prices"
    )


def chatbot_hosting_packages_text_ar() -> str:
    return (
        f"شهر واحد: {settings.chatbot_hosting_1_month_jod} ديناراً أردنياً؛ "
        f"3 أشهر: {settings.chatbot_hosting_3_months_jod} ديناراً؛ "
        f"6 أشهر: {settings.chatbot_hosting_6_months_jod} ديناراً؛ "
        f"12 شهراً: {settings.chatbot_hosting_12_months_jod} ديناراً، "
        "وتخضع جميع الأسعار لضريبة المبيعات"
    )


def graceful_closing_fallback(question: str) -> str:
    if answer_language(question) == "ar":
        return "للحصول على تفاصيل إضافية أو عرض مناسب لاحتياجات شركتك، يرجى التواصل مع فريق JorMall."
    return "For additional details or a solution tailored to your business, please contact the JorMall team."


def business_generation_fallback(question: str) -> str:
    if answer_language(question) == "ar":
        return (
            "يسعدنا مساعدتك في خدمات الرسائل داخل الأردن وخارجه، وربط الأنظمة عبر API، "
            "ورسائل OTP، وحلول الشات بوت. للحصول على التفاصيل الفنية والأسعار المناسبة "
            "لاحتياجات شركتك، يرجى التواصل مع فريق JorMall."
        )
    return (
        "JorMall can assist with messaging services, API integration, OTP messaging "
        "and chatbot solutions. Please contact the JorMall team for the technical "
        "details and pricing suitable for your business."
    )


def combine_partial_answer_with_graceful_fallback(question: str, partial_answer: str) -> str:
    clean_partial = (partial_answer or "").strip()
    fallback = graceful_closing_fallback(question)
    if not clean_partial:
        return business_generation_fallback(question)
    if fallback in clean_partial:
        return clean_partial
    return f"{clean_partial}\n\n{fallback}"


def has_meaningful_answer(text: str) -> bool:
    cleaned = re.sub(r"\s+", "", text or "")
    return len(cleaned) >= 12


def strip_old_unavailable_messages(text: str) -> str:
    cleaned = text or ""
    for old_message in OLD_UNAVAILABLE_MESSAGES:
        cleaned = cleaned.replace(old_message, "")
    return cleaned.strip()


PRICE_PATTERNS = (
    r"\b(price|prices|pricing|rate|rates|cost|costs|fee|fees|package|packages|how much|quotation|quote)\b",
    r"(?:سعر|اسعار|الاسعار|السعر|تكلفه|التكلفه|رسوم|الرسوم|باقه|باقات|عرض سعر|كم)",
)
CHATBOT_PATTERNS = (
    r"\b(chatbot|chat bot|bot setup|interactive chatbot|interactive sms chatbot|hosting)\b",
    r"(?:شات\s*بوت|الشات\s*بوت|بوت|روبوت\s*محادثه|الاستضافه|استضافه)",
)
HOSTING_PATTERNS = (
    r"\b(hosting|hosted|renewal package|hosting package|hosting packages)\b",
    r"(?:الاستضافه|استضافه|باقه الاستضافه|باقات الاستضافه)",
)
SMS_PATTERNS = (
    r"\b(bulk sms|ordinary sms|promotional sms|service sms|sms pricing|sms price|sms rates|message cost|messages?)\b",
    r"(?:sms|رسائل|رساله|مسجات|رسائل نصيه|الرسائل الدعائيه|الرسائل الخدميه|رسائل الاعلان)",
)
OTP_PATTERNS = (
    r"\b(otp|verification message|verification sms|otp sms)\b",
    r"(?:رمز التحقق|رسائل التحقق|رسائل otp|التحقق)",
)
INTERNATIONAL_PATTERNS = (
    r"\b(international sms|international messaging|outside jordan|outside of jordan|destinations?|countries|operators?)\b",
    r"(?:دوليه|الدوليه|خارج الاردن|الدول|الوجهات|شبكه الاتصالات)",
)
API_PATTERNS = (
    r"\b(api|integration|integrate|connect my system|system integration)\b",
    r"(?:api|ربط|الربط|تكامل|نظام|الانظمه)",
)
WHATSAPP_PATTERNS = (
    r"\b(whatsapp|whats app|whatsapp business api)\b",
    r"(?:واتساب|واتس اب)",
)


def detect_pricing_intent(question: str) -> PricingIntent | None:
    text = normalized_text(question)
    language = answer_language(question)
    price_requested = has_any(text, PRICE_PATTERNS)
    service_flags = {
        "sms": has_any(text, SMS_PATTERNS),
        "otp": has_any(text, OTP_PATTERNS),
        "international": has_any(text, INTERNATIONAL_PATTERNS),
        "api": has_any(text, API_PATTERNS),
        "chatbot": has_any(text, CHATBOT_PATTERNS),
        "whatsapp": has_any(text, WHATSAPP_PATTERNS),
    }
    requested_services = [name for name, matched in service_flags.items() if matched]
    hosting_requested = has_any(text, HOSTING_PATTERNS)
    explicit_chatbot_requested = has_any(
        text,
        (
            r"\b(chatbot|chat bot|bot setup|interactive chatbot|interactive sms chatbot)\b",
            r"(?:شات\s*بوت|الشات\s*بوت|بوت|روبوت\s*محادثه)",
        ),
    )

    broad_multi_service_request = len(requested_services) >= 3 or (
        service_flags["chatbot"] and len(requested_services) >= 2
    )
    if broad_multi_service_request and (
        price_requested
        or has_any(
            text,
            (
                r"\b(recommend|advise|need|want|provide|available|services?)\b",
                r"(?:تنصح|احتاج|بدي|اريد|عندكم|توفر|خدمات)",
            ),
        )
    ):
        return PricingIntent(category="mixed", language=language)

    if (
        hosting_requested
        and not explicit_chatbot_requested
        and service_flags["chatbot"]
        and len(requested_services) == 1
    ):
        return PricingIntent(category="hosting", language=language)

    if not price_requested:
        return None
    if service_flags["whatsapp"]:
        return PricingIntent(category="whatsapp", language=language)
    if service_flags["otp"]:
        return PricingIntent(category="otp", language=language)
    if service_flags["international"]:
        return PricingIntent(category="international_sms", language=language)
    if service_flags["api"] and not service_flags["chatbot"]:
        return PricingIntent(category="api", language=language)
    if service_flags["sms"] and not service_flags["chatbot"]:
        return PricingIntent(category="sms", language=language)
    if service_flags["chatbot"]:
        return PricingIntent(category="chatbot", language=language)
    return None


def chatbot_pricing_answer(language: str) -> str:
    if language == "ar":
        return (
            f"سعر إنشاء شات بوت الحملة التفاعلي هو {chatbot_setup_price_text_ar()}. "
            "يشمل السعر إنشاء شات بوت واحد وتهيئته واختباره وتفعيله، ورابطاً قابلاً للمشاركة، "
            "واستضافة لمدة شهر واحد من تاريخ التفعيل، ورسائل التفاعل والمعاملات عبر GPT خلال الشهر المشمول. "
            "مدة الإنشاء يوم عمل واحد بعد استلام معلومات الحملة الكاملة والمواد المطلوبة وموافقة العميل. "
            f"باقات الاستضافة بعد الشهر المشمول هي: {chatbot_hosting_packages_text_ar()}."
        )
    return (
        f"The Interactive Campaign Chatbot creation fee is {chatbot_setup_price_text_en()}. "
        "It includes creation, configuration, testing and activation of one campaign chatbot, "
        "a shareable link, one month of hosting from activation, and GPT interaction and transactional-message costs during that month. "
        "Creation takes one working day after JorMall receives the complete campaign information, required materials and client approval. "
        f"Hosting after the included month is available in these packages: {chatbot_hosting_packages_text_en()}."
    )


def chatbot_hosting_answer(language: str) -> str:
    if language == "ar":
        return (
            "يشمل سعر إنشاء شات بوت الحملة التفاعلي استضافة لمدة شهر واحد من تاريخ التفعيل، "
            "وتكون تكاليف رسائل التفاعل والمعاملات عبر GPT مشمولة خلال فترة الاستضافة الفعالة. "
            f"بعد الشهر المشمول، تتوفر باقات الاستضافة التالية: {chatbot_hosting_packages_text_ar()}. "
            "يجب تجديد الباقة قبل انتهائها لتجنب انقطاع الخدمة؛ فعند انتهاء الباقة دون تجديد "
            "تنتهي الاستضافة وتغطية رسائل GPT، وقد يتم تعطيل رابط الشات بوت."
        )
    return (
        "The chatbot creation fee includes one month of hosting from activation, with GPT "
        "interaction and transactional-message costs covered throughout the active hosting period. "
        f"After the included month, these hosting packages are available: {chatbot_hosting_packages_text_en()}. "
        "The package should be renewed before expiry to avoid interruption; if it expires without "
        "renewal, hosting and GPT message coverage end and the chatbot link may be deactivated."
    )


def sms_pricing_answer(language: str) -> str:
    if language == "ar":
        return (
            "أسعار رسائل SMS تختلف حسب نوع الرسائل، والكمية، والوجهة، والخدمة المطلوبة. "
            "المعلومات المتوفرة هنا تتضمن سعر إعداد الشات بوت فقط، لذلك يرجى التواصل مع فريق JorMall "
            "للحصول على أسعار وباقات SMS المناسبة لاحتياجاتكم."
        )
    return (
        "SMS pricing depends on the message type, volume, destination and required service. "
        "The information available here includes chatbot pricing only, so please contact the JorMall team "
        "for the appropriate SMS rates and packages."
    )


def otp_pricing_answer(language: str) -> str:
    if language == "ar":
        return (
            "تختلف أسعار رسائل OTP حسب حجم الاستخدام، والربط المطلوب، والوجهات. "
            "يرجى التواصل مع فريق JorMall للحصول على عرض سعر مناسب."
        )
    return (
        "OTP pricing depends on usage volume, integration requirements and destinations. "
        "Please contact the JorMall team for a suitable quotation."
    )


def international_sms_pricing_answer(language: str) -> str:
    if language == "ar":
        return (
            "تختلف أسعار الرسائل الدولية حسب الدولة، وشبكة الاتصالات، ونوع الرسالة، وحجم الإرسال. "
            "يرجى التواصل مع فريق JorMall لتحديد الدول المطلوبة والحصول على الأسعار المتاحة."
        )
    return (
        "International SMS rates vary by country, operator, message type and sending volume. "
        "Please contact the JorMall team with the required destinations to receive the available rates."
    )


def api_pricing_answer(language: str) -> str:
    if language == "ar":
        return (
            "تكلفة ربط API تعتمد على آلية الربط المطلوبة، وسير العمل، وحجم الرسائل، ونوع الخدمة. "
            "يرجى التواصل مع فريق JorMall لمراجعة المتطلبات الفنية وتقديم عرض مناسب."
        )
    return (
        "API integration costs depend on the required workflow, message volume and service type. "
        "Please contact the JorMall team for a technical review and suitable quotation."
    )


def whatsapp_pricing_answer(language: str) -> str:
    if language == "ar":
        return "بخصوص WhatsApp API، يرجى التواصل مع فريق JorMall للتأكد من التوفر والمتطلبات الحالية."
    return "For WhatsApp API availability and current requirements, please contact the JorMall team."


def mixed_services_answer(language: str) -> str:
    if language == "ar":
        return (
            "بناءً على احتياجات شركتك، يمكن تقسيم الحل إلى عدة أجزاء:\n\n"
            "- رسائل داخل الأردن: يتم تحديد المنصة ونوع الرسائل حسب ما إذا كانت دعائية أو خدمية.\n"
            "- رسائل خارج الأردن: يلزم تحديد الدول والكميات المطلوبة لأن التوفر والأسعار تختلف حسب الدولة وشبكة الاتصالات.\n"
            "- ربط API: يمكن دراسة آلية الربط مع نظامكم حسب العمليات التي تريدون تنفيذها.\n"
            "- رسائل OTP: مناسبة للتحقق من الحسابات وتسجيل الدخول والعمليات الحساسة، ويحتاج عرض السعر إلى معرفة حجم الاستخدام المتوقع.\n"
            f"- الشات بوت: يمكن ربط شات بوت تفاعلي بالحملات. سعر الإنشاء هو {chatbot_setup_price_text_ar()} ويشمل استضافة شهر واحد؛ وتتوفر بعد ذلك باقات استضافة منفصلة.\n"
            "- WhatsApp API: يرجى التواصل مع فريق JorMall للتأكد من التوفر والمتطلبات الحالية.\n\n"
            "ننصح بإعداد اجتماع قصير مع فريق JorMall لتحديد الدول، والكميات، وأنواع الرسائل، ومتطلبات الربط، ثم تقديم الحل والعرض المناسب."
        )
    return (
        "Based on your business needs, the solution can be reviewed in separate parts:\n\n"
        "- SMS inside Jordan: the platform and message type depend on whether the messages are promotional or service messages.\n"
        "- International SMS: required countries and volumes are needed because availability and rates vary by destination and operator.\n"
        "- API integration: the workflow can be reviewed according to the operations you want to connect with your system.\n"
        "- OTP messages: suitable for account verification, login and sensitive actions; pricing depends on expected usage volume.\n"
        f"- Chatbot: an interactive campaign chatbot can be connected to advertising messages. The creation fee is {chatbot_setup_price_text_en()}, including one month of hosting; separate renewal packages are available afterward.\n"
        "- WhatsApp API: please contact the JorMall team to confirm availability and current requirements.\n\n"
        "A short review with the JorMall team is recommended to confirm destinations, volumes, message types and integration requirements, then prepare the suitable solution and quotation."
    )


def deterministic_pricing_answer(question: str) -> str | None:
    greeting_answer = greeting_only_answer(question)
    if greeting_answer is not None:
        return greeting_answer

    greeting = split_leading_greeting(question)
    substantive_question = greeting[2] if greeting and greeting[2] else question
    intent = detect_pricing_intent(substantive_question)
    if intent is None:
        return None
    if intent.category == "mixed":
        return prefix_answer_for_leading_greeting(question, mixed_services_answer(intent.language))
    if intent.category == "sms":
        return prefix_answer_for_leading_greeting(question, sms_pricing_answer(intent.language))
    if intent.category == "otp":
        return prefix_answer_for_leading_greeting(question, otp_pricing_answer(intent.language))
    if intent.category == "international_sms":
        return prefix_answer_for_leading_greeting(question, international_sms_pricing_answer(intent.language))
    if intent.category == "api":
        return prefix_answer_for_leading_greeting(question, api_pricing_answer(intent.language))
    if intent.category == "whatsapp":
        return prefix_answer_for_leading_greeting(question, whatsapp_pricing_answer(intent.language))
    if intent.category == "chatbot":
        return prefix_answer_for_leading_greeting(question, chatbot_pricing_answer(intent.language))
    if intent.category == "hosting":
        return prefix_answer_for_leading_greeting(question, chatbot_hosting_answer(intent.language))
    return None
