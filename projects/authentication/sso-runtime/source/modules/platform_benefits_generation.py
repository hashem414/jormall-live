import json
import os
import re
from copy import deepcopy
from pathlib import Path
from .openai_client import create_openai_client



INDUSTRY_AR = {
    "Healthcare": "الرعاية الصحية",
    "Retail & Consumer Goods": "التجزئة والسلع الاستهلاكية",
    "Automotive": "السيارات",
    "Banking & Financial Services": "البنوك والخدمات المالية",
    "Education": "التعليم",
    "Government & Public Sector": "الحكومة والقطاع العام",
    "Hospitality & Tourism": "الضيافة والسياحة",
    "Restaurants & Food Services": "المطاعم وخدمات الأغذية",
    "Real Estate": "العقارات",
    "Insurance": "التأمين",
    "E-commerce": "التجارة الإلكترونية",
    "Telecom & Technology": "الاتصالات والتكنولوجيا",
    "Professional Services": "الخدمات المهنية",
    "Logistics & Delivery": "الخدمات اللوجستية والتوصيل",
    "Beauty, Wellness & Fitness": "الجمال والعافية واللياقة",
    "Other": "قطاعات أخرى",
}

SUPPORTED_INDUSTRIES = [
    "Healthcare",
    "Retail & Consumer Goods",
    "Automotive",
    "Banking & Financial Services",
    "Education",
    "Government & Public Sector",
    "Hospitality & Tourism",
    "Restaurants & Food Services",
    "Real Estate",
    "Insurance",
    "E-commerce",
    "Telecom & Technology",
    "Professional Services",
    "Logistics & Delivery",
    "Beauty, Wellness & Fitness",
    "Other",
]

# Facts in this block are intentionally limited to the capabilities explicitly
# represented by the approved Platform Benefits example supplied for this feature.
JOR_MALL_PLATFORM_FACTS = """
Use only these JorMall platform facts. Do not invent prices, SLAs, integrations, legal claims, or product capabilities beyond them:
- Account management and bulk SMS sending to approved lists or selected audience segments.
- Message creation, scheduling, campaign automation, list/segment management, and classifications.
- Delivery monitoring and immediate campaign reports.
- Interactive links can point to booking/confirmation, registration forms, location pages, surveys, campaign/service pages, or other relevant client pages.
- JorMall documentation states that broader campaigns may use an organized Jordan mobile database of more than 7.5 million users, segmented by attributes such as age, gender, education, geography, income, and interests.
- Arabic and English campaigns can be prepared according to the audience.
- Campaign performance can be measured through delivery, link clicks, resulting actions, registrations/bookings/inquiries, and completed surveys where applicable.
- Messages must be classified correctly as service, awareness, or promotional, and campaigns must follow Jordan TRC requirements including content restrictions, sending timing, unsubscribe requests, and customer privacy. The approved example also states no sending on Fridays and official holidays.
- JorMall documentation describes fast delivery through direct links with the main telecom operators in Jordan, more than two decades of experience, advanced targeting, real-time reporting, regulatory compliance, and customer support.
- In addition to industry-specific communication, the requested Platform Benefits document must always include company-wide operational SMS use cases for Finance and Human Resources. Keep these messages non-sensitive; where confidential details are involved, point the recipient to an approved secure company channel or portal rather than placing confidential data in the SMS body.
""".strip()


AR_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


def get_openai_client():
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    return create_openai_client(api_key)


def _is_arabic(value):
    return str(value or "").strip().lower() in {"ar", "arabic", "العربية", "عربي"}


def _clean_text(value, max_chars=None):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not max_chars or len(text) <= max_chars:
        return text
    clipped = text[: max_chars + 1]
    # Prefer a natural stop before the limit when possible.
    stop = max(clipped.rfind(". "), clipped.rfind("، "), clipped.rfind("; "), clipped.rfind(". "))
    if stop >= max_chars * 0.65:
        clipped = clipped[: stop + 1]
    else:
        clipped = clipped[:max_chars].rstrip(" ,،;:-")
    return clipped


def _ensure_list(value, fallback, count, max_chars):
    items = value if isinstance(value, list) else []
    cleaned = [_clean_text(x, max_chars) for x in items if _clean_text(x)]
    fallback_clean = [_clean_text(x, max_chars) for x in fallback if _clean_text(x)]
    for item in fallback_clean:
        if len(cleaned) >= count:
            break
        cleaned.append(item)
    return cleaned[:count]


def _extract_json_object(text):
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError("Model did not return a valid JSON object")


def _safe_filename(value):
    value = re.sub(r"[^\w\-]+", "_", str(value or ""), flags=re.UNICODE).strip("_")
    return value[:70] or "Company"


def _company_context(company_url=None, company_about=None):
    if company_about and company_about.strip():
        return "Manual Description", company_about.strip()[:14000]
    if company_url and company_url.strip():
        url = company_url.strip()
        try:
            from .website_crawler_scrapper import crawl_entire_domain_as_text, fetch_website_text
        except Exception as exc:
            print(f"[Platform Benefits] website crawler unavailable: {exc}")
            return url, ""
        try:
            text = crawl_entire_domain_as_text(url, max_pages=8, max_text_length=1800)
            if text and "No Data found" not in text and len(text.strip()) > 80:
                return url, text[:14000]
        except Exception as exc:
            print(f"[Platform Benefits] domain crawl failed: {exc}")
        try:
            text = fetch_website_text(url, max_length=14000)
            return url, text[:14000]
        except Exception as exc:
            print(f"[Platform Benefits] fallback website fetch failed: {exc}")
            return url, ""
    return "N/A", ""


def _fallback_payload(company_name, industry, language):
    ar = _is_arabic(language)
    c = company_name
    i = INDUSTRY_AR.get(industry, industry) if ar else industry
    if ar:
        return {
            "cover_title_line_1": f"كيف تستفيد {c}",
            "cover_title_line_2": "من خدمة رسائل منصة جورمول SMS",
            "cover_subtitle": f"منظومة اتصال عملية ومباشرة مصممة لقطاع {i}",
            "page2_title": f"رسائل SMS كقناة اتصال لـ {c}",
            "page2_tagline": "تواصل مباشر ومنظم مع العملاء والمستفيدين وفق نوع العلاقة والاحتياج",
            "role_heading": f"دور رسائل SMS في دعم تجربة العميل وعمليات {i}",
            "role_paragraphs": [
                f"يمكن لـ {c} استخدام منصة جورمول كقناة اتصال مباشرة ومنظمة للوصول إلى العملاء والمستفيدين وربط الرسائل بمراحل الخدمة أو الشراء أو المتابعة.",
                "تساعد الرسائل النصية على إرسال التذكيرات والتحديثات، توجيه الجمهور إلى الروابط والخدمات الإلكترونية، وجمع الملاحظات بعد التفاعل.",
            ],
            "platform_question": "ما الذي توفره منصة جورمول؟",
            "platform_bullets": [
                "إدارة الحساب وإرسال رسائل الجملة إلى قوائم محددة أو شرائح مختارة.",
                "إنشاء الرسائل، الجدولة، أتمتة الحملات، وإدارة الشرائح والتصنيفات.",
                "متابعة التسليم والتقارير الفورية لقياس أداء الحملة.",
                f"استخدام الرسائل بما يخدم أهداف قطاع {i} من تواصل وخدمة وتوعية وتسويق.",
            ],
            "segmentation_heading": f"إدارة التصنيفات داخل المنصة لـ {c}",
            "segmentation_intro": "يمكن تقسيم قاعدة البيانات إلى شرائح واضحة حتى تصل الرسالة المناسبة إلى الفئة المناسبة بدلاً من إرسال رسالة عامة للجميع.",
            "segmentation_bullets": [
                "عملاء حاليون بحسب نوع الخدمة أو المنتج أو المرحلة الحالية.",
                "عملاء محتملون بحسب الاهتمام أو المنطقة أو مصدر الطلب.",
                "مستفيدون يحتاجون إلى متابعة أو تذكير أو استبيان رضا.",
                "مسجلون في فعالية أو عرض أو نشاط تنظمه الشركة.",
                "شركات أو مجموعات يتم التواصل معها ضمن حملات مخصصة عند الحاجة.",
            ],
            "segmentation_note_label": "ميزة التقسيم",
            "segmentation_note": "يساعد على تخصيص الرسائل حسب العلاقة والمرحلة والحملة، ما يرفع وضوح التواصل ويقلل الإرسال غير الضروري.",
            "common_needs_heading": "احتياجات رسائل مشتركة لكل شركة: المالية والموارد البشرية",
            "common_needs_intro": "إلى جانب الاستخدامات المرتبطة بالقطاع، تحتاج الشركات عادةً إلى رسائل تشغيلية مشتركة لدعم أعمال الإدارة المالية والموارد البشرية والتواصل الداخلي.",
            "finance_heading": "رسائل الإدارة المالية",
            "finance_bullets": [
                "تنبيهات الاستحقاقات والفواتير أو الدفعات المطلوبة للجهات المعنية.",
                "تأكيد استلام دفعة أو اكتمال إجراء مالي دون تضمين بيانات مالية حساسة.",
                "إشعار بأن كشفاً أو مستنداً مالياً أصبح متاحاً عبر القناة أو النظام المعتمد.",
                "تذكير الموظفين أو الموردين بإجراءات مالية داخلية ومواعيد تقديم المطالبات أو المستندات.",
            ],
            "finance_message": f"نحيطكم علماً من {c} بأن [الإجراء/المستند المالي] أصبح جاهزاً. للتفاصيل يرجى استخدام القناة المعتمدة: [الرابط/الرقم].",
            "hr_heading": "رسائل الموارد البشرية",
            "hr_bullets": [
                "تذكير الموظفين بمواعيد التدريب والاجتماعات والتقييمات والإجراءات المطلوبة.",
                "إشعارات الجداول أو المناوبات أو تغييرات أوقات العمل للفئات المعنية.",
                "رسائل الترحيب بالموظفين الجدد وربطهم بصفحة التعليمات أو إجراءات الانضمام.",
                "تنبيهات الإجازات والسياسات والنماذج والمواعيد الإدارية دون إرسال بيانات شخصية حساسة.",
            ],
            "hr_message": f"رسالة من الموارد البشرية في {c}: نذكّركم بـ [الموعد/الإجراء] بتاريخ [التاريخ]. للتفاصيل أو استكمال الإجراء: [الرابط].",
            "common_needs_note": "عند ارتباط الرسالة ببيانات مالية أو وظيفية سرية، يفضل أن تكون الرسالة إشعاراً مختصراً وتوجّه المستلم إلى نظام أو قناة آمنة معتمدة للاطلاع على التفاصيل.",
            "campaigns_title": "نماذج حملات SMS مقترحة",
            "campaigns_tagline": f"أمثلة قابلة للتخصيص بحسب إجراءات {c} وطبيعة قطاع {i}",
            "campaigns": [
                {"title": "تأكيد الطلب أو الحجز", "objective": "رفع وضوح الخطوة التالية وتقليل الاستفسارات المتكررة.", "message": f"تم تأكيد طلبكم لدى {c}. لمراجعة التفاصيل أو إدارة الطلب: [الرابط/الرقم]."},
                {"title": "تذكير بموعد أو استحقاق", "objective": "تحسين الالتزام بالمواعيد أو الخطوات المطلوبة.", "message": f"نذكّركم بموعدكم/استحقاقكم لدى {c} يوم [التاريخ] الساعة [الوقت]. للتفاصيل: [الرابط]."},
                {"title": "متابعة رضا العميل", "objective": "جمع ملاحظات قابلة للقياس حول تجربة العميل.", "message": f"نشكركم لتعاملكم مع {c}. رأيكم يساعدنا على تحسين تجربتكم. شاركونا تقييمكم: [رابط الاستبيان]."},
                {"title": "دعوة إلى عرض أو فعالية", "objective": "زيادة الوصول والحضور أو الاستفادة من النشاط المعلن.", "message": f"تدعوكم {c} إلى [اسم العرض/الفعالية] يوم [التاريخ]. للتسجيل ومعرفة التفاصيل: [الرابط]."},
                {"title": "إعلان خدمي أو تحديث مهم", "objective": "إيصال التحديثات المهمة بسرعة وبصياغة موحدة.", "message": f"نحيطكم علماً بأن [الخدمة/التحديث] لدى {c} سيكون متاحاً في [الأيام/الساعات]. للاستفسار: [الرابط/الرقم]."},
            ],
            "execution_title": "آلية التنفيذ عبر منصة جورمول",
            "execution_tagline": "مسار واضح من تجهيز القوائم وحتى متابعة نتائج الإرسال",
            "execution_heading": "خطوات التنفيذ",
            "execution_steps": [
                "تجهيز قاعدة البيانات: تحميل القوائم المعتمدة وتحديث بيانات التواصل للفئات المستهدفة.",
                "تقسيم الجمهور: تصنيف القوائم حسب نوع العميل أو الخدمة أو الحملة أو المرحلة.",
                "اختيار نوع الرسالة: تأكيد، تذكير، دعوة، تسجيل، استبيان، تحديث خدمي أو رسالة توعوية.",
                "إضافة رابط تفاعلي: رابط طلب أو حجز أو تسجيل أو موقع أو استبيان أو صفحة تعريفية.",
                "جدولة الإرسال: إرسال الرسالة في التوقيت المناسب وإضافة رسائل متابعة عند الحاجة.",
                "متابعة التقارير: مراجعة التسليم والتفاعل مع الروابط ومؤشرات الحملة.",
            ],
            "journey_heading": "سيناريو عملي لدورة تواصل العميل",
            "journey_bullets": [
                "بعد الطلب أو التسجيل: رسالة تأكيد تتضمن المعلومات الأساسية ورابط الإدارة.",
                "قبل الموعد أو الاستحقاق: رسالة تذكير مختصرة وواضحة.",
                "عند الحاجة: رابط مباشر للتعديل أو الاستفسار أو استكمال الإجراء.",
                "بعد الخدمة: رسالة شكر قصيرة مع رابط استبيان رضا أو متابعة.",
            ],
            "journey_note": "بهذه الدورة تصبح SMS جزءاً من رحلة العميل وليست رسالة منفردة، ويمكن قياس أثر كل نقطة اتصال وتحسينها.",
            "links_heading": "روابط تفاعلية مناسبة",
            "links_bullets": [
                "طلب أو حجز أو تأكيد.",
                "صفحة موقع واتجاهات الوصول أو الفروع.",
                "استبيان رضا أو ملاحظات بعد الخدمة.",
                "صفحة تسجيل لفعالية أو حملة.",
                "صفحة تعريفية بخدمة أو منتج أو تعليمات مهمة.",
            ],
            "measurement_title": "الاستهداف والقياس والتوصية التنفيذية",
            "measurement_tagline": "تحويل الرسائل من قناة إرسال إلى أداة اتصال قابلة للقياس",
            "advanced_heading": f"خدمات متقدمة مناسبة لـ {c}",
            "advanced_paragraphs": [
                "عند الحاجة إلى حملات أوسع خارج قاعدة بيانات الشركة، توضح وثائق جورمول أن لديها قاعدة بيانات منظمة تضم أكثر من 7.5 مليون مستخدم موبايل في الأردن ويمكن تقسيمها وفق خصائص متعددة.",
                f"يمكن الاستفادة من هذا الاستهداف في حملات قطاع {i} بعد تحديد المنطقة والفئة المناسبة وهدف الحملة قبل الإرسال.",
            ],
            "advanced_bullets": [
                "حملات مخصصة باللغة العربية أو الإنجليزية بحسب الجمهور.",
                "جدولة الرسائل وربطها بروابط تسجيل أو طلب أو استبيان.",
                "تقارير فورية لمتابعة التسليم وقياس النتائج.",
            ],
            "kpi_heading": "مؤشرات قياس النجاح",
            "kpi_bullets": [
                "عدد الرسائل المرسلة ونسبة التسليم.",
                "عدد النقرات على الروابط التفاعلية.",
                "عدد الطلبات أو الحجوزات أو التسجيلات الناتجة بعد الرسالة.",
                "معدل الاستجابة مقارنة بالفترة السابقة للحملة.",
                "عدد الاستبيانات المكتملة وملاحظات رضا العملاء.",
                "عدد الاستفسارات أو العملاء المحتملين الناتجين عن الحملة.",
            ],
            "recommendation_heading": f"توصية تنفيذية لـ {c}",
            "recommendation_steps": [
                "مسار الخدمة: بدء رسائل التأكيد والتذكير للعمليات الأساسية المتكررة.",
                "مسار تجربة العميل: إرسال رسالة شكر واستبيان بعد الخدمة لقياس الرضا.",
                "مسار التوعية والعروض: استخدام حملات دورية للفئات المناسبة وفق هدف واضح.",
                "مسار الإعلانات الخدمية: إرسال التحديثات المهمة للفئات المعنية فقط.",
            ],
            "recommendation_note": "يفضل أن تبدأ كل حملة بهدف واحد واضح، وفئة محددة، ورسالة قصيرة، ورابط واحد أساسي عند الحاجة، ثم تقييم النتائج قبل توسيع النطاق.",
            "compliance_title": "الامتثال والتنظيم",
            "compliance_tagline": "تشغيل مهني ومتوافق مع متطلبات تنظيم حملات الرسائل",
            "compliance_heading": "ملاحظة امتثال وتنظيم",
            "compliance_paragraphs": [
                "يجب تصنيف الرسائل بشكل صحيح حسب محتواها، سواء كانت خدمية أو توعوية أو دعائية، مع الالتزام بتعليمات هيئة تنظيم قطاع الاتصالات الأردنية (TRC) المتعلقة بالمحتوى والتوقيت وإلغاء الاشتراك والخصوصية.",
                "وتوضح وثائق جورمول المعتمدة أيضاً حظر الإرسال في أيام الجمعة والعطل الرسمية.",
            ],
            "about_heading": "نبذة عن خدمة الرسائل النصية من جورمول",
            "about_paragraph": "جورمول مزود لحلول الرسائل النصية الجماعية في الأردن ويخدم قطاعات متنوعة. وبخبرة تمتد لأكثر من عقدين، تركز الخدمة على حملات موجهة تتناسب مع احتياجات كل عميل.",
            "about_bullets": [
                "موثوقية التسليم: إرسال سريع من خلال الربط المباشر مع شركات الاتصالات الرئيسية في الأردن.",
                "الاستهداف المتقدم: الاستفادة من قواعد بيانات شاملة ومقسمة لاستهداف أدق.",
                "الحملات المخصصة: محتوى رسائل بالعربية والإنجليزية وفق احتياج العميل والجمهور.",
                "التقارير الفورية: مؤشرات أداء وإمكانات تتبع تساعد على قياس فعالية الحملة.",
                "الامتثال التنظيمي: الالتزام بإرشادات هيئة تنظيم قطاع الاتصالات الأردنية (TRC).",
                "دعم العملاء: فريق متخصص للمساعدة في إعداد الحملات وتحسينها وإدارتها.",
            ],
        }

    return {
        "cover_title_line_1": f"How {c} can benefit",
        "cover_title_line_2": "from JorMall SMS Platform Services",
        "cover_subtitle": f"A practical communication system tailored to the {i} industry",
        "page2_title": f"SMS as a communication channel for {c}",
        "page2_tagline": "Direct, organized communication with customers and stakeholders based on relationship and need",
        "role_heading": f"The role of SMS in customer experience and {i} operations",
        "role_paragraphs": [
            f"{c} can use JorMall as a direct and organized communication channel to reach customers and stakeholders and connect messages to key service, sales, or follow-up stages.",
            "SMS can deliver reminders and updates, guide audiences to digital links and services, and collect feedback after an interaction.",
        ],
        "platform_question": "What does the JorMall platform provide?",
        "platform_bullets": [
            "Account management and bulk SMS sending to approved lists or selected audience groups.",
            "Message creation, scheduling, campaign automation, and audience segmentation/classification.",
            "Delivery monitoring and immediate campaign reporting.",
            f"SMS use cases tailored to communication, service, awareness, and marketing needs in {i}.",
        ],
        "segmentation_heading": f"Audience segmentation inside the platform for {c}",
        "segmentation_intro": "The database can be divided into clear groups so the right message reaches the right audience instead of sending one general message to everyone.",
        "segmentation_bullets": [
            "Existing customers grouped by service, product, or current stage.",
            "Potential customers grouped by interest, area, or lead source.",
            "Customers requiring a follow-up, reminder, or satisfaction survey.",
            "People registered for an event, offer, or activity organized by the company.",
            "Companies or groups contacted through tailored campaigns when needed.",
        ],
        "segmentation_note_label": "Segmentation benefit",
        "segmentation_note": "It supports more relevant messaging by relationship, stage, and campaign, improving clarity and reducing unnecessary sends.",
        "common_needs_heading": "Company-wide SMS needs: Finance and Human Resources",
        "common_needs_intro": "Alongside industry-specific communication, most companies have recurring operational messaging needs across Finance and Human Resources that can be supported through structured SMS communication.",
        "finance_heading": "Finance SMS",
        "finance_bullets": [
            "Reminders for invoices, payment due dates, or required financial actions to the relevant recipients.",
            "Confirmation that a payment or financial process was received or completed without exposing sensitive financial data.",
            "Notification that a statement or financial document is available through the approved company channel.",
            "Internal reminders for employees or suppliers about claims, documents, or finance-related deadlines.",
        ],
        "finance_message": f"Notice from {c}: your [financial action/document] is ready. Please use the approved channel for details: [link/number].",
        "hr_heading": "Human Resources SMS",
        "hr_bullets": [
            "Reminders for training, meetings, evaluations, and required employee actions.",
            "Shift, schedule, or working-hours notifications for the relevant employee groups.",
            "New-employee welcome messages linked to onboarding instructions or required steps.",
            "Leave, policy, form, and administrative deadline reminders without including sensitive personal information.",
        ],
        "hr_message": f"HR notice from {c}: reminder for [appointment/action] on [date]. For details or to complete the required step: [link].",
        "common_needs_note": "When a message relates to confidential financial or employment information, keep the SMS brief and direct the recipient to an approved secure company system or channel for the details.",
        "campaigns_title": "Suggested SMS campaign models",
        "campaigns_tagline": f"Examples that can be customized to {c} processes and the {i} industry",
        "campaigns": [
            {"title": "Order or booking confirmation", "objective": "Clarify the next step and reduce repeated questions.", "message": f"Your request with {c} is confirmed. Review details or manage your request here: [link/number]."},
            {"title": "Appointment or due-date reminder", "objective": "Improve completion of appointments or required actions.", "message": f"Reminder from {c}: your appointment/due action is on [date] at [time]. Details: [link]."},
            {"title": "Post-service satisfaction follow-up", "objective": "Collect measurable feedback about the customer experience.", "message": f"Thank you for choosing {c}. Your feedback helps us improve. Share your experience here: [survey link]."},
            {"title": "Offer or event invitation", "objective": "Increase reach, attendance, or participation in a promoted activity.", "message": f"{c} invites you to [offer/event] on [date]. Register or view details: [link]."},
            {"title": "Service announcement or important update", "objective": "Deliver important updates quickly with consistent wording.", "message": f"Update from {c}: [service/update] will be available on [days/hours]. For details: [link/number]."},
        ],
        "execution_title": "Implementation through the JorMall platform",
        "execution_tagline": "A clear path from preparing lists to reviewing campaign results",
        "execution_heading": "Implementation steps",
        "execution_steps": [
            "Prepare the database: upload approved lists and update contact information for target groups.",
            "Segment the audience: classify lists by customer type, service, campaign, or stage.",
            "Choose the message type: confirmation, reminder, invitation, registration, survey, service update, or awareness message.",
            "Add an interactive link: order, booking, registration, location, survey, or service/campaign page.",
            "Schedule delivery: send at the appropriate time and add follow-up messages when needed.",
            "Review reports: monitor delivery, link engagement, and campaign indicators.",
        ],
        "journey_heading": "Practical customer communication journey",
        "journey_bullets": [
            "After an order or registration: send a confirmation with key details and a management link.",
            "Before an appointment or due action: send a concise reminder.",
            "When needed: provide a direct link for changes, inquiries, or completion of the action.",
            "After service: send a short thank-you with a satisfaction or follow-up link.",
        ],
        "journey_note": "This makes SMS part of the customer journey rather than a standalone message, allowing each touchpoint to be measured and improved.",
        "links_heading": "Suitable interactive links",
        "links_bullets": [
            "Order, booking, or confirmation page.",
            "Location, directions, or branch page.",
            "Satisfaction survey or feedback page.",
            "Registration page for an event or campaign.",
            "Service/product information page or important instructions.",
        ],
        "measurement_title": "Targeting, measurement, and executive recommendation",
        "measurement_tagline": "Turning SMS from a sending channel into a measurable communication tool",
        "advanced_heading": f"Advanced services suitable for {c}",
        "advanced_paragraphs": [
            "For broader campaigns beyond the company database, JorMall documentation states that it has an organized Jordan mobile database of more than 7.5 million users that can be segmented by multiple attributes.",
            f"This type of targeting can support {i} campaigns after defining the campaign objective, geography, and suitable audience before sending.",
        ],
        "advanced_bullets": [
            "Arabic or English campaigns according to the target audience.",
            "Scheduled messages connected to registration, request, booking, or survey links.",
            "Immediate reports for delivery monitoring and result measurement.",
        ],
        "kpi_heading": "Success measurement indicators",
        "kpi_bullets": [
            "Number of messages sent and delivery rate.",
            "Number of clicks on interactive links.",
            "Orders, bookings, registrations, or other actions completed after the message.",
            "Response rate compared with the pre-campaign period.",
            "Completed surveys and customer satisfaction feedback.",
            "New inquiries or leads generated by the campaign.",
        ],
        "recommendation_heading": f"Executive recommendation for {c}",
        "recommendation_steps": [
            "Service path: start with confirmation and reminder messages for recurring core processes.",
            "Customer-experience path: send a thank-you and post-service survey to measure satisfaction.",
            "Awareness and promotion path: run periodic campaigns for clearly defined relevant audiences.",
            "Service-announcement path: send important operational updates only to the affected groups.",
        ],
        "recommendation_note": "Each campaign should begin with one clear objective, one defined audience, a short message, and one primary link when needed, then be evaluated before scaling.",
        "compliance_title": "Compliance and operational requirements",
        "compliance_tagline": "Professional operation aligned with messaging campaign requirements",
        "compliance_heading": "Compliance and operational note",
        "compliance_paragraphs": [
            "Messages should be correctly classified as service, awareness, or promotional, and campaigns should follow Jordan TRC requirements for content, timing, unsubscribe requests, and customer privacy.",
            "The approved JorMall example for this feature also states that sending is prohibited on Fridays and official holidays.",
        ],
        "about_heading": "About JorMall SMS services",
        "about_paragraph": "JorMall provides bulk SMS solutions in Jordan across multiple industries. With more than two decades of experience, the service focuses on high-quality, targeted campaigns tailored to each client's business needs.",
        "about_bullets": [
            "Delivery reliability: fast sending through direct links with the main telecom operators in Jordan.",
            "Advanced targeting: segmented databases support more precise audience selection.",
            "Customized campaigns: Arabic and English SMS content according to client and audience needs.",
            "Immediate reporting: performance indicators and tracking capabilities support campaign measurement.",
            "Regulatory compliance: alignment with Jordan Telecommunications Regulatory Commission (TRC) guidance.",
            "Customer support: a specialized team assists with campaign setup, optimization, and management.",
        ],
    }


def _build_ai_prompt(company_name, industry, language, source_label, context):
    ar = _is_arabic(language)
    language_name = "Arabic" if ar else "English"
    example = _fallback_payload(company_name, industry, language)
    keys = list(example.keys())
    return f"""
You are preparing a client-facing JorMall document titled "Platform Benefits".

Company: {company_name}
Industry: {industry}
Company source: {source_label}
Company context (use only if it actually supports the statement):
{context[:14000]}

{JOR_MALL_PLATFORM_FACTS}

Goal:
Create a concise client-facing content package showing how the company can benefit from JorMall's SMS platform. Use the approved hospital Platform Benefits document as the CONTENT reference only: preserve its practical structure and depth (platform role, segmentation, campaign models, implementation, interactive links, targeting, measurement, recommendations, and compliance), but do not imitate or depend on that document's visual style. Tailor the content to the selected industry and company context when available. Do not copy hospital-specific wording unless the selected company is in healthcare.

Language: {language_name}
Mandatory rules:
- Return ONE valid JSON object only. No Markdown fences and no commentary.
- Use every key listed below and no additional top-level keys.
- Keep wording concise so it fits a six-page A4 Word layout.
- Never invent prices, discounts, guarantees, integrations, client statistics, or legal/regulatory facts beyond the provided JorMall platform facts.
- If the company website/context does not support a company-specific detail, keep the statement industry-level rather than guessing.
- Use exactly 5 campaign objects, exactly 6 execution steps, exactly 4 journey bullets, exactly 5 link bullets, exactly 6 KPI bullets, and exactly 4 recommendation steps.
- Always include the Finance and Human Resources section, regardless of industry. Finance must have exactly 4 bullets and one practical SMS example; Human Resources must have exactly 4 bullets and one practical SMS example.
- Do not create a summary or conclusion section. End the generated analysis content with compliance/operational requirements; the shared JorMall document renderer may still add its standard About JorMall page.
- Each campaign object must have exactly: title, objective, message.
- SMS examples should be practical, include placeholders such as [link], [date], [time], [number] where helpful, and should not promise unavailable capabilities.
- For Arabic, write polished Modern Standard Arabic and translate all headings/labels; English may appear only in brand names, SMS, TRC, URLs, emails, and unavoidable terms.

Top-level keys:
{json.dumps(keys, ensure_ascii=False)}

Length guidance:
- titles/taglines/headings: <= 110 characters
- normal paragraphs: <= 330 characters each
- bullets/steps: <= 190 characters each
- campaign objective: <= 170 characters
- campaign message: <= 230 characters
- Finance/HR intro or note: <= 330 characters
- Finance/HR bullets: <= 190 characters each
- Finance/HR SMS examples: <= 230 characters
- about paragraph: <= 430 characters

Return the JSON now.
""".strip()


def _normalize_payload(raw, fallback):
    data = deepcopy(fallback)
    if not isinstance(raw, dict):
        return data

    scalar_limits = {
        "cover_title_line_1": 110, "cover_title_line_2": 110, "cover_subtitle": 180,
        "page2_title": 120, "page2_tagline": 180, "role_heading": 120,
        "platform_question": 100, "segmentation_heading": 120, "segmentation_intro": 330,
        "segmentation_note_label": 55, "segmentation_note": 260,
        "common_needs_heading": 120, "common_needs_intro": 330, "finance_heading": 90,
        "finance_message": 230, "hr_heading": 90, "hr_message": 230, "common_needs_note": 330,
        "campaigns_title": 110, "campaigns_tagline": 180, "execution_title": 110,
        "execution_tagline": 180, "execution_heading": 100, "journey_heading": 110,
        "journey_note": 280, "links_heading": 100, "measurement_title": 120,
        "measurement_tagline": 180, "advanced_heading": 120, "kpi_heading": 100,
        "recommendation_heading": 125, "recommendation_note": 300, "compliance_title": 100,
        "compliance_tagline": 170, "compliance_heading": 100,
        "about_heading": 110, "about_paragraph": 430,
    }
    for key, limit in scalar_limits.items():
        value = _clean_text(raw.get(key), limit)
        if value:
            data[key] = value

    list_specs = {
        "role_paragraphs": (2, 330),
        "platform_bullets": (4, 190),
        "segmentation_bullets": (5, 190),
        "finance_bullets": (4, 190),
        "hr_bullets": (4, 190),
        "execution_steps": (6, 190),
        "journey_bullets": (4, 190),
        "links_bullets": (5, 175),
        "advanced_paragraphs": (2, 350),
        "advanced_bullets": (3, 180),
        "kpi_bullets": (6, 175),
        "recommendation_steps": (4, 210),
        "compliance_paragraphs": (2, 360),
        "about_bullets": (6, 190),
    }
    for key, (count, limit) in list_specs.items():
        data[key] = _ensure_list(raw.get(key), fallback[key], count, limit)

    campaigns = raw.get("campaigns") if isinstance(raw.get("campaigns"), list) else []
    normalized_campaigns = []
    for index in range(5):
        fb = fallback["campaigns"][index]
        candidate = campaigns[index] if index < len(campaigns) and isinstance(campaigns[index], dict) else {}
        normalized_campaigns.append({
            "title": _clean_text(candidate.get("title"), 110) or fb["title"],
            "objective": _clean_text(candidate.get("objective"), 170) or fb["objective"],
            "message": _clean_text(candidate.get("message"), 230) or fb["message"],
        })
    data["campaigns"] = normalized_campaigns
    return data


def _platform_content_to_analysis(content, company_name, industry, language):
    """Convert Platform Benefits content into the shared client-insight markdown structure.

    The Platform Benefits source document is used as a content reference only. The
    shared Client Profile / Marketing Plan renderer remains responsible for style.
    """
    ar = _is_arabic(language)

    def bullets(items):
        return "\n".join(f"- {str(item).strip()}" for item in (items or []) if str(item).strip())

    def numbered(items):
        return "\n".join(
            f"{i}. {str(item).strip()}" for i, item in enumerate(items or [], 1) if str(item).strip()
        )

    if ar:
        sector = INDUSTRY_AR.get(industry, industry)
        overview = (
            f"**الشركة:** {company_name}\n"
            f"**القطاع:** {sector}\n\n"
            f"### {content['role_heading']}\n"
            + "\n\n".join(content.get('role_paragraphs', []))
            + f"\n\n### {content['platform_question']}\n"
            + bullets(content.get('platform_bullets'))
            + f"\n\n### {content['segmentation_heading']}\n"
            + content.get('segmentation_intro', '')
            + "\n\n" + bullets(content.get('segmentation_bullets'))
            + f"\n\n**{content['segmentation_note_label']}:** {content['segmentation_note']}"
        )

        common_needs = (
            f"{content.get('common_needs_intro', '')}\n\n"
            f"### {content.get('finance_heading', 'رسائل الإدارة المالية')}\n"
            + bullets(content.get('finance_bullets'))
            + f"\n\n**نموذج رسالة:** {content.get('finance_message', '')}\n\n"
            + f"### {content.get('hr_heading', 'رسائل الموارد البشرية')}\n"
            + bullets(content.get('hr_bullets'))
            + f"\n\n**نموذج رسالة:** {content.get('hr_message', '')}\n\n"
            + f"**ملاحظة تشغيلية:** {content.get('common_needs_note', '')}"
        )

        campaign_lines = [content.get('campaigns_tagline', '')]
        for i, campaign in enumerate(content.get('campaigns', []), 1):
            campaign_lines.extend([
                f"\n### {i}. {campaign.get('title', '')}",
                f"**الهدف:** {campaign.get('objective', '')}",
                f"**نموذج رسالة:** {campaign.get('message', '')}",
            ])
        campaigns_text = "\n".join(campaign_lines)

        execution = (
            f"{content.get('execution_tagline', '')}\n\n"
            f"### {content['execution_heading']}\n{numbered(content.get('execution_steps'))}\n\n"
            f"### {content['journey_heading']}\n{bullets(content.get('journey_bullets'))}\n\n"
            f"{content.get('journey_note', '')}\n\n"
            f"### {content['links_heading']}\n{bullets(content.get('links_bullets'))}"
        )

        measurement = (
            f"{content.get('measurement_tagline', '')}\n\n"
            f"### {content['advanced_heading']}\n"
            + "\n\n".join(content.get('advanced_paragraphs', []))
            + "\n\n" + bullets(content.get('advanced_bullets'))
            + f"\n\n### {content['kpi_heading']}\n{bullets(content.get('kpi_bullets'))}\n\n"
            + f"### {content['recommendation_heading']}\n{numbered(content.get('recommendation_steps'))}\n\n"
            + content.get('recommendation_note', '')
        )

        compliance = (
            f"{content.get('compliance_tagline', '')}\n\n"
            f"### {content['compliance_heading']}\n"
            + "\n\n".join(content.get('compliance_paragraphs', []))
        )

        return {
            "platform_overview": {
                "header": "فوائد منصة جورمول",
                "original_header": "Platform Benefits Overview",
                "answer": overview,
            },
            "finance_hr": {
                "header": content.get('common_needs_heading', 'احتياجات رسائل مشتركة لكل شركة: المالية والموارد البشرية'),
                "original_header": "Company-wide SMS Needs: Finance and Human Resources",
                "answer": common_needs,
            },
            "campaign_models": {
                "header": content.get('campaigns_title', 'نماذج حملات SMS مقترحة'),
                "original_header": "Suggested SMS Campaign Models",
                "answer": campaigns_text,
            },
            "implementation": {
                "header": content.get('execution_title', 'آلية التنفيذ عبر منصة جورمول'),
                "original_header": "Implementation through JorMall",
                "answer": execution,
            },
            "measurement": {
                "header": content.get('measurement_title', 'الاستهداف والقياس والتوصية التنفيذية'),
                "original_header": "Targeting, Measurement and Executive Recommendation",
                "answer": measurement,
            },
            "compliance": {
                "header": content.get('compliance_title', 'الامتثال والتنظيم'),
                "original_header": "Compliance and Operational Requirements",
                "answer": compliance,
            },
        }

    overview = (
        f"**Company:** {company_name}\n"
        f"**Industry:** {industry}\n\n"
        f"### {content['role_heading']}\n"
        + "\n\n".join(content.get('role_paragraphs', []))
        + f"\n\n### {content['platform_question']}\n"
        + bullets(content.get('platform_bullets'))
        + f"\n\n### {content['segmentation_heading']}\n"
        + content.get('segmentation_intro', '')
        + "\n\n" + bullets(content.get('segmentation_bullets'))
        + f"\n\n**{content['segmentation_note_label']}:** {content['segmentation_note']}"
    )

    common_needs = (
        f"{content.get('common_needs_intro', '')}\n\n"
        f"### {content.get('finance_heading', 'Finance SMS')}\n"
        + bullets(content.get('finance_bullets'))
        + f"\n\n**Message sample:** {content.get('finance_message', '')}\n\n"
        + f"### {content.get('hr_heading', 'Human Resources SMS')}\n"
        + bullets(content.get('hr_bullets'))
        + f"\n\n**Message sample:** {content.get('hr_message', '')}\n\n"
        + f"**Operational note:** {content.get('common_needs_note', '')}"
    )

    campaign_lines = [content.get('campaigns_tagline', '')]
    for i, campaign in enumerate(content.get('campaigns', []), 1):
        campaign_lines.extend([
            f"\n### {i}. {campaign.get('title', '')}",
            f"**Objective:** {campaign.get('objective', '')}",
            f"**Message sample:** {campaign.get('message', '')}",
        ])
    campaigns_text = "\n".join(campaign_lines)

    execution = (
        f"{content.get('execution_tagline', '')}\n\n"
        f"### {content['execution_heading']}\n{numbered(content.get('execution_steps'))}\n\n"
        f"### {content['journey_heading']}\n{bullets(content.get('journey_bullets'))}\n\n"
        f"{content.get('journey_note', '')}\n\n"
        f"### {content['links_heading']}\n{bullets(content.get('links_bullets'))}"
    )

    measurement = (
        f"{content.get('measurement_tagline', '')}\n\n"
        f"### {content['advanced_heading']}\n"
        + "\n\n".join(content.get('advanced_paragraphs', []))
        + "\n\n" + bullets(content.get('advanced_bullets'))
        + f"\n\n### {content['kpi_heading']}\n{bullets(content.get('kpi_bullets'))}\n\n"
        + f"### {content['recommendation_heading']}\n{numbered(content.get('recommendation_steps'))}\n\n"
        + content.get('recommendation_note', '')
    )

    compliance = (
        f"{content.get('compliance_tagline', '')}\n\n"
        f"### {content['compliance_heading']}\n"
        + "\n\n".join(content.get('compliance_paragraphs', []))
    )

    return {
        "platform_overview": {
            "header": "Platform Benefits",
            "original_header": "Platform Benefits Overview",
            "answer": overview,
        },
        "finance_hr": {
            "header": content.get('common_needs_heading', 'Company-wide SMS Needs: Finance and Human Resources'),
            "original_header": "Company-wide SMS Needs: Finance and Human Resources",
            "answer": common_needs,
        },
        "campaign_models": {
            "header": content.get('campaigns_title', 'Suggested SMS Campaign Models'),
            "original_header": "Suggested SMS Campaign Models",
            "answer": campaigns_text,
        },
        "implementation": {
            "header": content.get('execution_title', 'Implementation through the JorMall Platform'),
            "original_header": "Implementation through JorMall",
            "answer": execution,
        },
        "measurement": {
            "header": content.get('measurement_title', 'Targeting, Measurement and Executive Recommendation'),
            "original_header": "Targeting, Measurement and Executive Recommendation",
            "answer": measurement,
        },
        "compliance": {
            "header": content.get('compliance_title', 'Compliance and Operational Requirements'),
            "original_header": "Compliance and Operational Requirements",
            "answer": compliance,
        },
    }

def run_platform_benefits_generation(company_name, industry, report_language, json_path, company_url=None, company_about=None):
    language = "ar" if _is_arabic(report_language) else "en"
    fallback = _fallback_payload(company_name, industry, language)
    source_label, context = _company_context(company_url=company_url, company_about=company_about)

    generated = None
    try:
        prompt = _build_ai_prompt(company_name, industry, language, source_label, context)
        response = get_openai_client().chat.completions.create(
            model="gpt-5.5",
            messages=[
                {
                    "role": "system",
                    "content": "You create concise, accurate JorMall client proposals. Follow the supplied platform facts exactly and return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        generated = _extract_json_object(response.choices[0].message.content)
    except Exception as exc:
        # A deterministic fallback still produces a useful document if the AI API
        # is temporarily unavailable or returns malformed JSON.
        print(f"[Platform Benefits] AI generation fallback used: {exc}")

    content = _normalize_payload(generated, fallback)
    payload = {
        "platform_benefits": True,
        "company_name": company_name,
        "industry": industry,
        "company_source": source_label,
        "report_language": "Arabic" if language == "ar" else "English",
        "document_language": language,
        "content": content,
        "analysis": _platform_content_to_analysis(content, company_name, industry, language),
    }
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload
