import ast
import json
import os
import re
from pathlib import Path
from .openai_client import create_openai_client


PRODUCTS = {
    "reservation_chatbot": {
        "en": "Reservation Chatbot",
        "ar": "مساعد الحجوزات الذكي",
    },
    "campaign_chatbot": {
        "en": "Campaign Chatbot",
        "ar": "مساعد الحملات الذكي",
    },
}


def _is_arabic(value):
    return str(value or "").strip().lower() in {"ar", "arabic", "العربية", "عربي"}


def _get_openai_client():
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    return create_openai_client(api_key)


def _company_context(company_url=None, company_about=None):
    if company_about and company_about.strip():
        return "Manual Description", company_about.strip()[:14000]
    if company_url and company_url.strip():
        url = company_url.strip()
        try:
            from .website_crawler_scrapper import crawl_entire_domain_as_text, fetch_website_text
            try:
                text = crawl_entire_domain_as_text(url, max_pages=8, max_text_length=1800)
                if text and "No Data found" not in text and len(text.strip()) > 80:
                    return url, text[:14000]
            except Exception as exc:
                print(f"[AI Products] domain crawl failed: {exc}")
            try:
                text = fetch_website_text(url, max_length=14000)
                return url, (text or "")[:14000]
            except Exception as exc:
                print(f"[AI Products] website fetch failed: {exc}")
        except Exception as exc:
            print(f"[AI Products] website crawler unavailable: {exc}")
        return url, ""
    return "N/A", ""


def _extract_json(text):
    if isinstance(text, dict):
        return text
    if isinstance(text, list):
        # Some SDK/content modes may return structured parts. Prefer a direct
        # object when present, otherwise combine textual parts for JSON parsing.
        for item in text:
            if isinstance(item, dict) and any(k in item for k in ("overview_title", "benefits", "conversation_examples")):
                return item
        pieces = []
        for item in text:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict):
                part_text = item.get("text") or item.get("content")
                if isinstance(part_text, str):
                    pieces.append(part_text)
        text = "\n".join(pieces)
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
    raise ValueError("Model did not return valid JSON")


def _humanize_key(key):
    return re.sub(r"[_-]+", " ", str(key or "")).strip().capitalize()


def _structured_to_text(value, depth=0):
    """Convert model JSON values to clean prose without leaking Python/JSON reprs.

    The AI occasionally returns an object inside a field that was requested as a
    string list (for example {"title": "...", "description": "..."}).  Calling
    str() on that value exposed raw output such as ``{'title': ...}`` in the Word
    document.  This function deliberately flattens structured values into readable
    text before rendering.
    """
    if value is None:
        return ""
    if depth > 4:
        return ""
    if isinstance(value, str):
        text = value.strip()
        # Handle a structured value that arrived double-encoded as a string.
        if len(text) >= 2 and text[0] in "[{" and text[-1] in "]}":
            parsed = None
            try:
                parsed = json.loads(text)
            except Exception:
                try:
                    parsed = ast.literal_eval(text)
                except Exception:
                    parsed = None
            if parsed is not None and not isinstance(parsed, str):
                return _structured_to_text(parsed, depth + 1)
        return text
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            text = _structured_to_text(item, depth + 1)
            if text and text not in parts:
                parts.append(text)
        return "; ".join(parts)
    if isinstance(value, dict):
        # Prefer common title/body pairs so the result reads naturally.
        title_keys = (
            "title", "name", "label", "heading", "topic", "type", "benefit",
            "use_case", "step", "action", "metric", "item", "requirement",
            "result", "goal", "purpose",
        )
        body_keys = ("description", "details", "detail", "text", "content", "value", "explanation", "example")
        title = next((_structured_to_text(value.get(k), depth + 1) for k in title_keys if value.get(k) not in (None, "")), "")
        body_parts = []
        for k in body_keys:
            if k in value and value.get(k) not in (None, ""):
                text = _structured_to_text(value.get(k), depth + 1)
                if text and text != title and text not in body_parts:
                    body_parts.append(text)
        if title and body_parts:
            return f"{title}: {' — '.join(body_parts)}"
        if title:
            remaining = []
            for k, v in value.items():
                if k in title_keys or v in (None, ""):
                    continue
                text = _structured_to_text(v, depth + 1)
                if text and text != title and text not in remaining:
                    remaining.append(text)
            return f"{title}: {' — '.join(remaining)}" if remaining else title
        if body_parts:
            return " — ".join(body_parts)

        # Unknown object shape: preserve the useful values with readable labels,
        # never the raw braces/quotes representation.
        parts = []
        for k, v in value.items():
            text = _structured_to_text(v, depth + 1)
            if not text:
                continue
            label = _humanize_key(k)
            parts.append(f"{label}: {text}" if label else text)
        return " — ".join(parts)
    return str(value).strip()


def _clean(value, max_chars=1200):
    text = _structured_to_text(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars].rstrip()


def _list(value, fallback, count=6, max_chars=260):
    # A single object/string is accepted as one candidate; expected lists remain lists.
    if isinstance(value, list):
        values = value
    elif value in (None, ""):
        values = []
    else:
        values = [value]
    result = []
    for item in values + list(fallback):
        item = _clean(item, max_chars)
        if item and item not in result:
            result.append(item)
        if len(result) >= count:
            break
    return result


def _reservation_fallback(company_name, language):
    c = company_name
    if language == "ar":
        return {
            "overview_title": "كيف يخدم مساعد الحجوزات الذكي الشركة",
            "overview_paragraphs": [
                f"يمكن لـ {c} استخدام مساعد الحجوزات الذكي من جورمول لتسهيل انتقال العميل من الاستفسار إلى طلب الحجز ضمن محادثة واضحة ومباشرة.",
                "يعمل المستند كتصور تشغيلي للمنتج: ما الذي يجيب عنه المساعد، وما البيانات التي يحتاجها، وكيف يوجّه العميل إلى خطوة حجز أو تواصل قابلة للمتابعة.",
            ],
            "benefits_heading": "الفوائد العملية",
            "benefits": [
                "استقبال طلبات الحجز والاستفسارات في أي وقت تتوفر فيه قناة المساعد.",
                "تقليل الأسئلة المتكررة حول الخدمات والمواعيد والموقع وساعات العمل.",
                "جمع معلومات الحجز الأساسية بصورة منظمة قبل تحويل الطلب إلى الفريق عند الحاجة.",
                "توجيه العميل إلى الإجراء التالي بوضوح: اختيار خدمة، طلب موعد، تأكيد بيانات، أو التواصل مع الموظف المختص.",
                "تقديم إجابات موحدة مبنية على المحتوى المعتمد من الشركة.",
            ],
            "use_cases_heading": "سيناريوهات الاستخدام",
            "use_cases": [
                "عميل يريد معرفة الخدمات المتاحة قبل اختيار ما يريد حجزه.",
                "عميل يسأل عن ساعات العمل أو الموقع أو وسائل التواصل.",
                "عميل يريد تقديم طلب حجز جديد أو طلب تغيير موعد قائم.",
                "عميل يحتاج معرفة التعليمات أو المتطلبات الإدارية المرتبطة بالزيارة عندما تكون معتمدة في قاعدة المعرفة.",
                "عميل يريد التحدث مع موظف عند وجود حالة لا يمكن للمساعد حسمها.",
            ],
            "flow_heading": "رحلة المحادثة المقترحة",
            "flow_steps": [
                "الترحيب بالعميل وتحديد الغرض من المحادثة.",
                "تحديد الخدمة أو نوع الحجز المطلوب.",
                "الإجابة عن الأسئلة الأساسية من قاعدة المعرفة المعتمدة.",
                "جمع بيانات الحجز المطلوبة فقط مثل الاسم ووسيلة التواصل والخدمة والموعد المفضل بحسب إعداد المشروع.",
                "عرض الخطوة التالية بوضوح: إرسال طلب الحجز، رابط الحجز، أو التحويل إلى الفريق.",
                "تأكيد ما تم تقديمه للعميل دون ادعاء تأكيد موعد نهائي ما لم يكن النظام المتصل قد أكده فعلاً.",
            ],
            "knowledge_heading": "المحتوى المطلوب لتجهيز المساعد",
            "knowledge": [
                "قائمة الخدمات أو أنواع المواعيد التي يمكن السؤال عنها.",
                "ساعات العمل والفروع والمواقع ووسائل التواصل.",
                "سياسة الحجز والتعديل والإلغاء إن وجدت.",
                "الأسئلة الشائعة والتعليمات المعتمدة قبل أو بعد الزيارة عند الحاجة.",
                "بيانات الأطباء أو الموظفين أو الأقسام فقط إذا كانت الشركة ترغب بعرضها ومعلوماتها معتمدة.",
                "آلية التحويل إلى موظف أو قناة خارجية للحالات التي تحتاج تدخلاً بشرياً.",
            ],
            "conversation_heading": "أمثلة محادثة",
            "conversation_examples": [
                {"customer": "أريد حجز موعد، ما الخدمات المتاحة؟", "assistant": "أستطيع مساعدتك في التعرف على الخدمات المتاحة ثم تسجيل طلب الحجز. ما نوع الخدمة التي تبحث عنها؟"},
                {"customer": "متى تفتحون؟", "assistant": "سأعطيك ساعات العمل المعتمدة للفرع المطلوب. أي فرع تقصد؟"},
                {"customer": "أريد تغيير موعدي.", "assistant": "يمكنني توجيهك إلى طريقة تعديل الموعد المعتمدة أو جمع المعلومات اللازمة لطلب التعديل."},
            ],
            "implementation_heading": "آلية التنفيذ",
            "implementation_steps": [
                "جمع واعتماد محتوى الشركة الذي سيجيب عنه المساعد.",
                "تحديد حقول الحجز المطلوبة ومسار التحويل إلى الفريق.",
                "إعداد المعرفة والأسئلة الشائعة ورسائل الترحيب والحالات الاستثنائية.",
                "اختبار سيناريوهات الحجز والأسئلة المتكررة والتحويل البشري.",
                "اعتماد النسخة النهائية ثم إطلاقها على القناة المحددة.",
                "مراجعة المحادثات والأسئلة غير المجابة لتحديث المحتوى بمرور الوقت.",
            ],
            "measurement_heading": "القياس والمتابعة",
            "measurement": [
                "عدد المحادثات التي بدأت بطلب حجز أو استفسار عن خدمة.",
                "عدد طلبات الحجز أو التحويلات إلى قناة الحجز.",
                "نسبة المحادثات التي وصلت إلى خطوة واضحة دون تدخل بشري.",
                "أكثر الأسئلة تكراراً والأسئلة التي تحتاج إضافة محتوى.",
                "عدد التحويلات إلى موظف والأسباب الرئيسية للتحويل.",
            ],
            "launch_heading": "قائمة اعتماد العميل قبل الإطلاق",
            "launch_checklist": [
                "اعتماد الخدمات أو أنواع المواعيد التي يمكن للمساعد ذكرها.",
                "اعتماد حقول طلب الحجز والبيانات التي يسمح بجمعها.",
                "اعتماد ساعات العمل والفروع وبيانات التواصل المعروضة.",
                "تحديد الحالات التي يجب تحويلها إلى موظف أو قناة رسمية.",
                "اختبار أمثلة المحادثة والتأكد من عدم وجود ادعاءات غير معتمدة قبل النشر.",
            ],
            "requirements_heading": "متطلبات تشغيلية مهمة",
            "requirements": [
                "المساعد يلتزم بالمعلومات المعتمدة ولا يخترع مواعيد أو أسعاراً أو سياسات غير موجودة في المصدر.",
                "أي بيانات شخصية يتم طلبها يجب أن تكون مرتبطة مباشرة بعملية الحجز وبالحد الأدنى اللازم.",
                "الحالات الحساسة أو غير الواضحة يتم تحويلها إلى قناة بشرية أو رسمية بدلاً من التخمين.",
                "يجب تحديث قاعدة المعرفة عند تغيير الخدمات أو ساعات العمل أو السياسات.",
            ],
        }
    return {
        "overview_title": "How the Reservation Chatbot Supports the Company",
        "overview_paragraphs": [
            f"{c} can use JorMall's Reservation Chatbot to move customers from questions to a booking request through a clear guided conversation.",
            "The document defines the practical product model: what the assistant should answer, what booking information it may collect, and how it directs customers to a measurable next step or human handoff.",
        ],
        "benefits_heading": "Practical Benefits",
        "benefits": [
            "Accept booking-related questions whenever the chatbot channel is available.",
            "Reduce repeated questions about services, availability guidance, location and working hours.",
            "Collect essential booking-request information in a consistent structure before handoff when needed.",
            "Guide each customer to a clear next action: choose a service, request a time, confirm details, or contact the relevant team.",
            "Provide consistent answers grounded in company-approved content.",
        ],
        "use_cases_heading": "Typical Use Cases",
        "use_cases": [
            "A customer wants to understand available services before deciding what to book.",
            "A customer asks about working hours, branches, location or contact options.",
            "A customer wants to submit a new booking request or ask how an existing appointment can be changed.",
            "A customer needs approved administrative pre-visit or post-visit instructions.",
            "A customer needs a human agent for a case the chatbot should not resolve on its own.",
        ],
        "flow_heading": "Suggested Conversation Journey",
        "flow_steps": [
            "Welcome the customer and identify the purpose of the conversation.",
            "Identify the requested service or booking type.",
            "Answer essential questions from the approved knowledge base.",
            "Collect only the configured booking fields such as name, contact method, service and preferred time.",
            "Present a clear next step: submit a booking request, open a booking link, or hand off to the team.",
            "Confirm what was submitted without claiming a final appointment is confirmed unless a connected booking system actually confirms it.",
        ],
        "knowledge_heading": "Content Required to Prepare the Chatbot",
        "knowledge": [
            "Approved services or appointment types.",
            "Working hours, branches, locations and contact channels.",
            "Booking, change and cancellation policies when applicable.",
            "Approved FAQs and pre/post-visit administrative guidance.",
            "Staff, doctor or department information only when the company wants it published and the data is approved.",
            "Human handoff or external channel rules for cases requiring staff assistance.",
        ],
        "conversation_heading": "Conversation Examples",
        "conversation_examples": [
            {"customer": "I want to book. What services are available?", "assistant": "I can help you review the available services and then submit a booking request. What type of service are you looking for?"},
            {"customer": "What time do you open?", "assistant": "I can share the approved working hours for the branch you need. Which branch are you asking about?"},
            {"customer": "I need to change my appointment.", "assistant": "I can guide you to the approved change process or collect the information needed for a change request."},
        ],
        "implementation_heading": "Implementation Workflow",
        "implementation_steps": [
            "Collect and approve the company content the chatbot is allowed to use.",
            "Define required booking fields and human-handoff rules.",
            "Configure knowledge, FAQs, welcome messages and exception handling.",
            "Test booking scenarios, frequent questions and escalation paths.",
            "Approve the final version and launch it on the selected channel.",
            "Review conversations and unanswered questions to improve the knowledge base over time.",
        ],
        "measurement_heading": "Measurement and Follow-up",
        "measurement": [
            "Number of conversations starting with a booking or service inquiry.",
            "Number of booking requests or transfers to the booking channel.",
            "Share of conversations reaching a clear next step without human intervention.",
            "Most frequent questions and questions that require new approved content.",
            "Number of human handoffs and the main reasons for escalation.",
        ],
        "launch_heading": "Client Approval Checklist Before Launch",
        "launch_checklist": [
            "Approve the services or appointment types the chatbot may mention.",
            "Approve the booking-request fields and data the chatbot may collect.",
            "Approve displayed working hours, branches and contact details.",
            "Define cases that must be handed to a staff member or official channel.",
            "Test conversation examples and confirm that no unapproved claims appear before launch.",
        ],
        "requirements_heading": "Important Operating Requirements",
        "requirements": [
            "The chatbot must stay within approved information and must not invent times, prices, policies or availability.",
            "Any personal data requested should be directly related to booking and limited to what is necessary.",
            "Sensitive or unclear cases should move to a human or official channel rather than being guessed.",
            "The knowledge base should be updated whenever services, hours or policies change.",
        ],
    }


def _campaign_fallback(company_name, language):
    c = company_name
    if language == "ar":
        return {
            "overview_title": "كيف يخدم مساعد الحملات الذكي الشركة",
            "overview_paragraphs": [
                f"يمكن لـ {c} استخدام مساعد الحملات الذكي من جورمول لإنشاء تجربة محادثة مخصصة لحملة واحدة أو عرض أو فعالية أو إطلاق خدمة محددة.",
                "بدلاً من أن تنتهي الرسالة أو الإعلان عند رابط ثابت، يستطيع العميل فتح محادثة تجيب عن تفاصيل الحملة المعتمدة، توضح الشروط، وتوجهه إلى التسجيل أو الحجز أو طلب التواصل.",
            ],
            "benefits_heading": "الفوائد العملية للحملة",
            "benefits": [
                "تحويل الحملة من رسالة أحادية الاتجاه إلى تجربة تفاعلية يمكن للعميل الاستفسار داخلها.",
                "توحيد الإجابات حول العرض أو المنتج أو الفعالية وفق المحتوى المعتمد.",
                "تقليل الضغط على فرق المبيعات وخدمة العملاء في الأسئلة المتكررة للحملة.",
                "توجيه العملاء إلى الإجراء المطلوب مثل التسجيل أو الحجز أو طلب الاتصال أو زيارة صفحة محددة.",
                "جمع مؤشرات على الأسئلة والاهتمامات الأكثر شيوعاً لتحسين الحملة.",
            ],
            "journey_heading": "رحلة العميل داخل الحملة",
            "journey_steps": [
                "يرى العميل رسالة SMS أو إعلاناً أو رابطاً مرتبطاً بالحملة.",
                "يفتح مساعد الحملة ويرى رسالة ترحيب مرتبطة باسم الحملة وهدفها.",
                "يختار من الأسئلة المقترحة أو يكتب سؤاله حول العرض أو المنتج أو الشروط.",
                "يجيب المساعد حصراً من المعرفة المعتمدة للحملة.",
                "يوجه العميل إلى الإجراء المطلوب: تسجيل، حجز، نموذج اهتمام، اتصال، أو صفحة معلومات.",
                "تُراجع الأسئلة والنتائج لتحسين المحتوى والحملة عند الحاجة.",
            ],
            "knowledge_heading": "المحتوى المطلوب لتجهيز مساعد الحملة",
            "knowledge": [
                "اسم الحملة وهدفها وفترة سريانها.",
                "المنتج أو الخدمة أو الفعالية التي يتم الترويج لها.",
                "العرض والأسعار أو الخصومات أو الشروط فقط إذا كانت معتمدة ومقدمة من العميل.",
                "الفئة المستهدفة والمناطق أو قنوات التوفر عندما تكون ذات صلة.",
                "الأسئلة الشائعة والاستثناءات والقيود والمعلومات التي يجب عدم الادعاء بها.",
                "روابط التسجيل أو الحجز أو التواصل أو الصفحة التعريفية المرتبطة بالحملة.",
            ],
            "conversation_heading": "أمثلة محادثة للحملة",
            "conversation_examples": [
                {"customer": "ما تفاصيل العرض؟", "assistant": "سأعرض لك تفاصيل العرض المعتمدة، فترة السريان، وأهم الشروط المتاحة في محتوى الحملة."},
                {"customer": "هل العرض متاح لي؟", "assistant": "يمكنني توضيح شروط الأهلية المعتمدة للحملة. إذا لم تكن الأهلية محددة في المحتوى فسأوجهك إلى الفريق للتأكيد."},
                {"customer": "كيف أسجل؟", "assistant": "يمكنك المتابعة عبر رابط التسجيل أو الإجراء المعتمد للحملة: [الرابط]."},
            ],
            "implementation_heading": "آلية التنفيذ",
            "implementation_steps": [
                "استلام المحتوى النهائي المعتمد للحملة من العميل.",
                "تحديد هدف المحادثة والإجراء الرئيسي الذي يجب أن يصل إليه المستخدم.",
                "إعداد قاعدة معرفة الحملة والأسئلة المقترحة ورسائل الترحيب والردود المقيدة.",
                "إضافة الروابط وقنوات التواصل التي يعتمدها العميل للحملة.",
                "اختبار الأسئلة المتوقعة والحالات التي يجب تحويلها إلى موظف.",
                "اعتماد المساعد وإطلاق الرابط ضمن قنوات الحملة ثم متابعة الاستخدام.",
            ],
            "measurement_heading": "القياس والمتابعة",
            "measurement": [
                "عدد فتحات المحادثة المرتبطة بالحملة.",
                "أكثر الأسئلة والموضوعات التي يهتم بها الجمهور.",
                "عدد النقرات أو الانتقالات إلى رابط التسجيل أو الحجز أو التواصل عندما يكون التتبع متاحاً.",
                "عدد طلبات التواصل أو العملاء المحتملين الناتجين عند تهيئة الحملة لذلك.",
                "الأسئلة التي لم تغطها المعرفة وتحتاج تحديثاً من العميل.",
            ],
            "launch_heading": "قائمة اعتماد الحملة قبل الإطلاق",
            "launch_checklist": [
                "اعتماد اسم الحملة وهدفها وتاريخ البداية والنهاية إن وجدت.",
                "اعتماد العرض أو الأسعار أو الخصومات أو شروط الأهلية التي سيذكرها المساعد.",
                "اعتماد روابط التسجيل أو الحجز أو التواصل والإجراء الرئيسي المطلوب.",
                "اعتماد الأسئلة الشائعة والاستثناءات والحالات التي تحتاج تحويلاً بشرياً.",
                "اختبار انتهاء الحملة أو تغير الشروط والتأكد من وجود آلية واضحة لتحديث المحتوى.",
            ],
            "requirements_heading": "متطلبات تشغيلية مهمة",
            "requirements": [
                "يجب أن تبقى إجابات المساعد ضمن نطاق الحملة ومحتواها المعتمد.",
                "لا يجوز اختراع أسعار أو خصومات أو شروط أو تواريخ أو مخزون لم يقدمه العميل.",
                "عند انتهاء الحملة أو تغيير شروطها يجب تحديث المساعد أو إيقاف المحتوى القديم.",
                "أي بيانات يتم جمعها من العميل يجب أن تكون مرتبطة بهدف الحملة وبما يتوافق مع القنوات والسياسات المعتمدة.",
            ],
        }
    return {
        "overview_title": "How the Campaign Chatbot Supports the Company",
        "overview_paragraphs": [
            f"{c} can use JorMall's Campaign Chatbot to create a focused conversation experience for one campaign, offer, event or service launch.",
            "Instead of ending at a static message or link, customers can open a campaign-specific assistant that explains approved details, answers campaign questions and directs them to registration, booking or a contact action.",
        ],
        "benefits_heading": "Practical Campaign Benefits",
        "benefits": [
            "Turn one-way campaign communication into an interactive question-and-answer experience.",
            "Keep answers about the offer, product or event consistent with approved campaign content.",
            "Reduce repeated campaign questions reaching sales or customer-service teams.",
            "Direct customers to the intended action such as registration, booking, contact request or a specific page.",
            "Reveal common questions and interests that can help improve campaign content.",
        ],
        "journey_heading": "Customer Journey Through the Campaign",
        "journey_steps": [
            "The customer receives an SMS, sees an ad, or opens a campaign link.",
            "The campaign assistant opens with a welcome message tied to the campaign name and objective.",
            "The customer selects a suggested question or asks about the offer, product, event or terms.",
            "The assistant answers only from the approved campaign knowledge.",
            "The customer is guided to the intended action: register, book, submit interest, call, or open an information page.",
            "Questions and outcomes are reviewed to improve the campaign when needed.",
        ],
        "knowledge_heading": "Content Required to Prepare the Campaign Chatbot",
        "knowledge": [
            "Campaign name, objective and validity period.",
            "Promoted product, service, event or launch.",
            "Offer, prices, discounts or terms only when they are approved and supplied by the client.",
            "Target audience, locations and availability channels when relevant.",
            "FAQs, exclusions, limitations and claims the assistant must not make.",
            "Registration, booking, contact or campaign-information links.",
        ],
        "conversation_heading": "Campaign Conversation Examples",
        "conversation_examples": [
            {"customer": "What are the offer details?", "assistant": "I can show you the approved offer details, validity period and the main terms included in the campaign content."},
            {"customer": "Am I eligible for the offer?", "assistant": "I can explain the approved eligibility conditions. If eligibility is not defined in the campaign content, I will direct you to the team for confirmation."},
            {"customer": "How do I register?", "assistant": "You can continue through the approved campaign registration action here: [link]."},
        ],
        "implementation_heading": "Implementation Workflow",
        "implementation_steps": [
            "Receive the client's final approved campaign content.",
            "Define the conversation objective and the primary customer action.",
            "Prepare the campaign knowledge base, starter questions, welcome messages and guardrails.",
            "Add the client-approved campaign links and contact channels.",
            "Test expected questions and cases that should be handed to a human.",
            "Approve and launch the assistant link through campaign channels, then review usage.",
        ],
        "measurement_heading": "Measurement and Follow-up",
        "measurement": [
            "Number of campaign chatbot sessions.",
            "Most common questions and audience interests.",
            "Clicks or transfers to registration, booking or contact links when tracking is available.",
            "Contact requests or leads generated when the campaign is configured for lead collection.",
            "Questions not covered by the knowledge base that require client-approved updates.",
        ],
        "launch_heading": "Campaign Approval Checklist Before Launch",
        "launch_checklist": [
            "Approve the campaign name, objective and start/end dates when applicable.",
            "Approve any offer, prices, discounts or eligibility terms the assistant may state.",
            "Approve registration, booking or contact links and the campaign's primary call to action.",
            "Approve FAQs, exclusions and the cases that require human handoff.",
            "Test campaign-expiry or changed-term scenarios and confirm how outdated content will be updated or disabled.",
        ],
        "requirements_heading": "Important Operating Requirements",
        "requirements": [
            "The assistant should remain within the campaign scope and approved content.",
            "It must not invent prices, discounts, terms, dates, availability or stock not supplied by the client.",
            "When the campaign ends or terms change, the chatbot should be updated or outdated content disabled.",
            "Any customer data collected should be relevant to the campaign objective and handled through approved channels and policies.",
        ],
    }


def _fallback(company_name, product_type, language):
    if product_type == "reservation_chatbot":
        return _reservation_fallback(company_name, language)
    return _campaign_fallback(company_name, language)


def _build_prompt(company_name, product_type, language, source_label, context):
    product_name = PRODUCTS[product_type]["ar" if language == "ar" else "en"]
    language_name = "Arabic" if language == "ar" else "English"
    structure = """
Return valid JSON only with exactly these keys:
overview_title, overview_paragraphs, benefits_heading, benefits,
use_cases_heading, use_cases, flow_heading, flow_steps,
knowledge_heading, knowledge, conversation_heading, conversation_examples,
implementation_heading, implementation_steps, measurement_heading, measurement,
launch_heading, launch_checklist, requirements_heading, requirements
""" if product_type == "reservation_chatbot" else """
Return valid JSON only with exactly these keys:
overview_title, overview_paragraphs, benefits_heading, benefits,
journey_heading, journey_steps, knowledge_heading, knowledge,
conversation_heading, conversation_examples, implementation_heading,
implementation_steps, measurement_heading, measurement,
launch_heading, launch_checklist, requirements_heading, requirements
"""
    return f"""
You are preparing a client-facing JorMall AI Products document for {company_name}.
Selected product: {product_name}
Output language: {language_name}
Company source: {source_label}
Company context:
{context[:12000] or '[No company context available beyond the company name.]'}

Use the supplied JorMall Platform Benefits example as a CONTENT-CONCEPT reference only: keep the same practical, company-tailored depth by explaining the role of the product, concrete use cases, operational workflow, customer journey, required source content, measurable outcomes, and operating requirements. Do not copy its SMS-specific wording and do not imitate a separate visual template; the application renderer controls document style.

Product rules:
- Reservation Chatbot: focus on answering approved booking/service questions, guiding booking requests, collecting only configured booking details, and human handoff when needed. Never claim a booking is confirmed unless a connected system actually confirms it.
- Campaign Chatbot: focus on one campaign/offer/event/service launch, answer only campaign-approved information, guide to campaign actions, and surface campaign questions/interests. Never invent prices, discounts, dates, eligibility, stock, terms, or availability.
- Do not invent integrations, prices, SLAs, live availability, legal claims, or capabilities that are not stated in the company context.
- Keep the document useful for a sales/client review: concise paragraphs, actionable bullets, and three short conversation examples.
- conversation_examples must be an array of exactly 3 objects with keys customer and assistant.
- Every other plural/list field in the requested JSON schema must be an array of plain strings only, never objects or nested dictionaries.
- Do not place JSON/Python object syntax, braces, key/value pairs, or code-formatted structures inside prose fields.
- All customer/company facts must come from the supplied context. If a detail is unavailable, keep the recommendation generic rather than guessing.
- Write all headings and prose in {language_name}. Brand names and URLs may remain in their original form.

{structure}
""".strip()


def _normalize(generated, fallback, product_type):
    g = generated if isinstance(generated, dict) else {}
    out = dict(fallback)
    text_keys = [
        "overview_title", "benefits_heading", "knowledge_heading", "conversation_heading",
        "implementation_heading", "measurement_heading", "launch_heading", "requirements_heading",
    ]
    if product_type == "reservation_chatbot":
        text_keys += ["use_cases_heading", "flow_heading"]
        list_keys = ["overview_paragraphs", "benefits", "use_cases", "flow_steps", "knowledge", "implementation_steps", "measurement", "launch_checklist", "requirements"]
    else:
        text_keys += ["journey_heading"]
        list_keys = ["overview_paragraphs", "benefits", "journey_steps", "knowledge", "implementation_steps", "measurement", "launch_checklist", "requirements"]
    for key in text_keys:
        if _clean(g.get(key), 300):
            out[key] = _clean(g[key], 300)
    for key in list_keys:
        out[key] = _list(g.get(key), fallback.get(key, []), count=len(fallback.get(key, [])) or 5)

    examples = g.get("conversation_examples") if isinstance(g.get("conversation_examples"), list) else []
    cleaned_examples = []
    for item in examples:
        if not isinstance(item, dict):
            continue
        customer = _clean(item.get("customer"), 260)
        assistant = _clean(item.get("assistant"), 420)
        if customer and assistant:
            cleaned_examples.append({"customer": customer, "assistant": assistant})
        if len(cleaned_examples) >= 3:
            break
    for item in fallback.get("conversation_examples", []):
        if len(cleaned_examples) >= 3:
            break
        cleaned_examples.append(item)
    out["conversation_examples"] = cleaned_examples[:3]
    return out


def _bullets(items):
    return "\n".join(f"- {item}" for item in (items or []))


def _numbered(items):
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items or [], 1))


def _examples(items, ar=False):
    blocks = []
    for i, item in enumerate(items or [], 1):
        if ar:
            blocks.append(f"### {i}. مثال محادثة\n**العميل:** {item.get('customer', '')}\n\n**المساعد:** {item.get('assistant', '')}")
        else:
            blocks.append(f"### {i}. Conversation Example\n**Customer:** {item.get('customer', '')}\n\n**Assistant:** {item.get('assistant', '')}")
    return "\n\n".join(blocks)


def _analysis(content, company_name, product_type, language):
    ar = language == "ar"
    if product_type == "reservation_chatbot":
        overview = (
            f"### {content['overview_title']}\n" + "\n\n".join(content["overview_paragraphs"]) +
            f"\n\n### {content['benefits_heading']}\n{_bullets(content['benefits'])}\n\n"
            f"### {content['use_cases_heading']}\n{_bullets(content['use_cases'])}"
        )
        journey = f"### {content['flow_heading']}\n{_numbered(content['flow_steps'])}"
        h1 = "فوائد المنتج وحالات الاستخدام" if ar else "Product Benefits and Use Cases"
        h2 = "رحلة الحجز والمحادثة" if ar else "Booking and Conversation Journey"
        original1 = "Product Benefits and Use Cases"
        original2 = "Booking and Conversation Journey"
    else:
        overview = (
            f"### {content['overview_title']}\n" + "\n\n".join(content["overview_paragraphs"]) +
            f"\n\n### {content['benefits_heading']}\n{_bullets(content['benefits'])}"
        )
        journey = f"### {content['journey_heading']}\n{_numbered(content['journey_steps'])}"
        h1 = "فوائد المنتج للحملة" if ar else "Campaign Product Benefits"
        h2 = "رحلة العميل داخل الحملة" if ar else "Campaign Customer Journey"
        original1 = "Campaign Product Benefits"
        original2 = "Campaign Customer Journey"

    knowledge = _bullets(content['knowledge'])
    conversations = _examples(content["conversation_examples"], ar=ar)
    implementation = _numbered(content['implementation_steps'])
    measurement = (
        f"### {content['measurement_heading']}\n{_bullets(content['measurement'])}\n\n"
        f"### {content['launch_heading']}\n{_bullets(content['launch_checklist'])}\n\n"
        f"### {content['requirements_heading']}\n{_bullets(content['requirements'])}"
    )
    return {
        "benefits": {"header": h1, "original_header": original1, "answer": overview},
        "journey": {"header": h2, "original_header": original2, "answer": journey},
        "knowledge": {"header": "المحتوى المطلوب لإعداد المساعد" if ar else "Content Required to Prepare the Chatbot", "original_header": "Content Required to Prepare the Chatbot", "answer": knowledge},
        "examples": {"header": "نماذج محادثة مقترحة" if ar else "Suggested Conversation Examples", "original_header": "Suggested Conversation Examples", "answer": conversations},
        "implementation": {"header": "آلية التنفيذ المقترحة" if ar else "Suggested Implementation Workflow", "original_header": "Suggested Implementation Workflow", "answer": implementation},
        "measurement": {"header": "القياس والمتطلبات التشغيلية" if ar else "Measurement and Operating Requirements", "original_header": "Measurement and Operating Requirements", "answer": measurement},
    }


def run_ai_product_generation(company_name, product_type, report_language, json_path, company_url=None, company_about=None):
    if product_type not in PRODUCTS:
        raise ValueError("Unsupported AI product type")
    language = "ar" if _is_arabic(report_language) else "en"
    fallback = _fallback(company_name, product_type, language)
    source_label, context = _company_context(company_url=company_url, company_about=company_about)

    generated = None
    try:
        prompt = _build_prompt(company_name, product_type, language, source_label, context)
        response = _get_openai_client().chat.completions.create(
            model="gpt-5.5",
            messages=[
                {"role": "system", "content": "Create accurate, concise JorMall client documents. Return valid JSON only and do not invent company facts."},
                {"role": "user", "content": prompt},
            ],
        )
        generated = _extract_json(response.choices[0].message.content)
    except Exception as exc:
        print(f"[AI Products] deterministic fallback used: {exc}")

    content = _normalize(generated, fallback, product_type)
    payload = {
        "ai_product": True,
        "ai_product_type": product_type,
        "ai_product_name": PRODUCTS[product_type]["ar" if language == "ar" else "en"],
        "company_name": company_name,
        "company_source": source_label,
        "report_language": "Arabic" if language == "ar" else "English",
        "document_language": language,
        "content": content,
        "analysis": _analysis(content, company_name, product_type, language),
    }
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload
