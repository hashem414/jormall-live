import re
# -*- coding: utf-8 -*-
"""Shared helpers for English/Arabic report generation."""

ARABIC_FINAL_INSTRUCTION = """

تعليمات نهائية ملزمة لإصدار المستند العربي:
- تجاهل أي تعليمات سابقة تطلب الرد باللغة الإنجليزية.
- اكتب الناتج باللغة العربية فقط، باستثناء الروابط، أرقام الهواتف، أسماء العلامات التجارية، وBitly إذا وجدت.
- أجب فقط عن السؤال أو القسم الحالي المطلوب. لا تعِد إنشاء بقية أقسام المستند، ولا تكرر أقساماً مثل نبذة عن الشركة أو هدف الحملة أو الجمهور المستهدف أو اقتراحات اليوم والوقت إلا إذا كان السؤال الحالي يطلبها صراحة.
- اجعل المستند العربي مطابقاً تقريباً للمستند الإنجليزي من حيث البنية، عدد الأقسام، عدد النقاط، والترتيب.
- اكتب ترجمة عربية شبه حرفية ومباشرة للمعنى الإنجليزي، بدون توسع، وبدون إضافة أفكار أو فقرات جديدة.
- اجعل الإجابات مختصرة ومهنية؛ لا تضف مقدمات عامة أو شروحات طويلة.
- ترجم العناوين والتسميات الثابتة إلى العربية بوضوح.
- في أقسام اقتراحات الرسائل العربية، اكتب نص الرسائل بالعربية فقط ولا تترك عبارات عروض إنجليزية داخل الرسالة. مثلاً: اكتب "خصومات حتى 75% على مختارات من المتاجر" بدلاً من "Sale up to 75% off on selected items"، واكتب "قسائم بقيمة 10 و25 و50 ديناراً" بدلاً من "JOD 50, 25, 10".
- إذا كان اسم العلامة التجارية له صياغة عربية واضحة، استخدمها داخل الرسائل العربية لتجنب مشاكل اتجاه النص، مثل "سيتي مول الأردن" بدلاً من "City Mall Jordan".
- أبقِ المحتوى الإنجليزي كما هو داخل الأقسام التي يحدد اسمها صراحة أنها باللغة الإنجليزية، مثل English SMS Suggestions وSocial Media Caption (English) وRadio scripts (English) وEnglish Opt-out SMS.
- لا تستخدم رموزاً تعبيرية أو زخارف.
"""


def normalize_output_language(output_language=None, document_language=None, language=None, default="en"):
    selected = output_language or document_language or language or default
    selected = str(selected or "").strip().lower()
    if selected in {"ar", "arabic", "arabic document", "arabic_document", "arabic docx", "arabic_docx", "العربية", "عربي"}:
        return "ar"
    return "en"


def force_arabic_question(question):
    return f"{question}\n{ARABIC_FINAL_INSTRUCTION}"


def localize_header(header):
    original = str(header or "").strip()
    exact = {
        "Company Overview": "نبذة عن الشركة",
        "Campaign Pitch": "العرض التسويقي للحملة",
        "Target Audience": "الجمهور المستهدف",
        "Day and Time Suggestions": "اقتراحات اليوم والوقت",
        "Arabic SMS Suggestions (Casual - 70 Characters)": "اقتراحات رسائل عربية عامة - 70 حرفاً",
        "Arabic SMS Suggestions (Formal - 70 Characters)": "اقتراحات رسائل عربية تسويقية - 70 حرفاً",
        "Arabic SMS Suggestions (Formal - 126 Characters)": "اقتراحات رسائل عربية طويلة - 126 حرفاً",
        "Arabic SMS Suggestions (Formal - Long SMS - 126 Characters)": "اقتراحات رسائل عربية طويلة - 126 حرفاً",
        "Arabic SMS Suggestions (Formal) – 126 Characters [2 Messages]": "اقتراحات رسائل عربية طويلة - 126 حرفاً",
        "English SMS Suggestions (160 Characters)": "English SMS Suggestions - 160 Characters",
        "Social Media Caption (English)": "منشور سوشال ميديا (بالإنجليزية)",
        "Social Media Caption (Arabic)": "منشور سوشال ميديا (بالعربية)",
        "Radio Announcement Script (English)": "نص إعلان إذاعي (بالإنجليزية)",
        "Radio Dialogue Script (English)": "نص حوار إذاعي (بالإنجليزية)",
        "Radio Dialogue Script (Arabic)": "نص حوار إذاعي (بالعربية)",
        "SMS Potential and Benefits": "فرص وفوائد الرسائل القصيرة",
        "Strategic Advantage": "الميزة الاستراتيجية",
        "SWOT Analysis": "تحليل SWOT",
        "SMS Content Strategy": "استراتيجية محتوى الرسائل القصيرة",
        "Target Audience Segmentation": "تقسيم الجمهور المستهدف",
        "SMS Timing Strategy (Scheduling)": "استراتيجية توقيت الرسائل",
        "Client Promotion Integration": "أفكار تفعيل العروض داخل المتجر",
        "Arabic Opt-out SMS": "رسالة إلغاء الاشتراك (بالعربية)",
        "English Opt-out SMS": "رسالة إلغاء الاشتراك (بالإنجليزية)",
    }
    if original in exact:
        return exact[original]
    translated = original
    replacements = [
        ("Company Overview", "نبذة عن الشركة"),
        ("Campaign Pitch", "العرض التسويقي للحملة"),
        ("Target Audience", "الجمهور المستهدف"),
        ("Day and Time Suggestions", "اقتراحات اليوم والوقت"),
        ("English SMS Suggestions", "English SMS Suggestions"),
        ("Arabic SMS Suggestions", "اقتراحات رسائل عربية"),
        ("Social Media Caption", "منشور سوشال ميديا"),
        ("Radio Announcement Script", "نص إعلان إذاعي"),
        ("Radio Dialogue Script", "نص حوار إذاعي"),
        ("SMS Potential and Benefits", "فرص وفوائد الرسائل القصيرة"),
        ("Strategic Advantage", "الميزة الاستراتيجية"),
        ("SWOT Analysis", "تحليل SWOT"),
        ("SMS Content Strategy", "استراتيجية محتوى الرسائل القصيرة"),
        ("Target Audience Segmentation", "تقسيم الجمهور المستهدف"),
        ("SMS Timing Strategy (Scheduling)", "استراتيجية توقيت الرسائل"),
        ("Client Promotion Integration", "أفكار تفعيل العروض داخل المتجر"),
        ("Campaign", "الحملة"),
        ("Message", "الرسالة"),
        ("Characters", "حرفاً"),
        ("Formal", "رسمية"),
        ("Casual", "عامية"),
        ("Long SMS", "رسالة طويلة"),
        ("English", "English"),
        ("Arabic", "عربية"),
    ]
    for old, new in replacements:
        translated = translated.replace(old, new)
    return translated


def arabic_plan_system_message():
    return """
أنت خبير تسويق ومبيعات محترف في الأردن.
أجب باللغة العربية فقط، وبأسلوب عملي ومهني ومباشر.
أجب عن القسم الحالي فقط، ولا تكرر أو تنشئ أقساماً أخرى من التقرير لم يطلبها السؤال الحالي.
اجعل الإجابة مختصرة وشبه ترجمة حرفية للمطلوب في النسخة الإنجليزية.
حافظ على نفس بنية المستند الإنجليزي ونفس عدد الأقسام والنقاط قدر الإمكان.
لا تضف أفكاراً أو فقرات أو مقدمات غير مطلوبة.
لا تستخدم رموزاً تعبيرية أو زخارف، ولا تضف اعتذارات أو شروحات غير مطلوبة.
ترجم التسميات الثابتة والعناوين إلى العربية، باستثناء أسماء الشركات والروابط وأرقام الهواتف.
"""



def _format_arabic_voucher_values(values):
    """Return Arabic-friendly voucher phrase from numeric JOD values."""
    nums = []
    for v in values:
        try:
            nums.append(int(str(v).strip()))
        except Exception:
            pass
    if not nums:
        return ""
    nums = sorted(set(nums))
    if len(nums) == 1:
        joined = str(nums[0])
    elif len(nums) == 2:
        joined = f"{nums[0]} و{nums[1]}"
    else:
        joined = " و".join(str(n) for n in nums)
    return f"قسائم بقيمة {joined} ديناراً"


def sanitize_arabic_sms_answer(answer):
    """Clean common mixed LTR/RTL offer fragments from Arabic SMS suggestions.

    This is intentionally conservative: it fixes repeated English offer fragments
    that confuse Word's bidi rendering, while keeping URLs, phone numbers, and
    unknown brand names untouched.
    """
    text = str(answer or "")
    if not text.strip():
        return text

    # Common brand transliterations that caused bidi problems in Arabic SMS lines.
    brand_replacements = {
        "City Mall Jordan": "سيتي مول الأردن",
        "City Mall": "سيتي مول",
    }
    for en, ar in brand_replacements.items():
        text = re.sub(re.escape(en), ar, text, flags=re.IGNORECASE)

    # Translate common English retail offer fragments into Arabic.
    text = re.sub(
        r"\bSale\s+up\s+to\s+(\d{1,3})\s*%\s+off\s+on\s+selected\s+items\b",
        r"خصومات حتى \1% على مختارات من المتاجر",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bup\s+to\s+(\d{1,3})\s*%\s+off\s+on\s+selected\s+items\b",
        r"خصومات حتى \1% على مختارات من المتاجر",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bSale\s+up\s+to\s+(\d{1,3})\s*%\s+off\b",
        r"خصومات حتى \1%",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bup\s+to\s+(\d{1,3})\s*%\s+off\b",
        r"خصومات حتى \1%",
        text,
        flags=re.IGNORECASE,
    )

    # Convert voucher fragments such as "JOD 50, 25, 10" or "50, 25, 10 JOD".
    def repl_jod_prefix(m):
        values = re.findall(r"\d+", m.group(1))
        return _format_arabic_voucher_values(values) or m.group(0)

    def repl_jod_suffix(m):
        values = re.findall(r"\d+", m.group(1))
        return _format_arabic_voucher_values(values) or m.group(0)

    text = re.sub(r"\bJOD\s*((?:\d+\s*,\s*)+\d+)", repl_jod_prefix, text, flags=re.IGNORECASE)
    text = re.sub(r"((?:\d+\s*,\s*)+\d+)\s*\bJOD\b", repl_jod_suffix, text, flags=re.IGNORECASE)
    text = re.sub(r"\bJOD\s*(\d+)\b", r"\1 ديناراً", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\d+)\s*JOD\b", r"\1 ديناراً", text, flags=re.IGNORECASE)

    # Clean very common leftover English connectors inside Arabic offer lines.
    text = re.sub(r"\s+and\s+", " و", text, flags=re.IGNORECASE)

    # Clean doubled spaces produced by replacements, without touching line breaks.
    text = "\n".join(re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.splitlines())
    return text
