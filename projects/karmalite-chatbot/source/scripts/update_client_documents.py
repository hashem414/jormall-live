"""Tailor the supplied JorMall client documents to the Karmalite chatbot.

The script changes text in place while retaining paragraph styles, run formatting,
table formatting, sections, headers, footers, images, and page setup.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
AR_PATH = ROOT / "Chatbot Generator Client Document AR - Karmalite.docx"
EN_PATH = ROOT / "Chatbot Generator Client Document EN - Karmalite.docx"


def set_text(paragraph, text: str) -> None:
    """Replace paragraph text while preserving its first run's formatting."""
    if not paragraph.runs:
        paragraph.add_run(text)
        return
    paragraph.runs[0].text = text
    for run in paragraph.runs[1:]:
        run.text = ""


def set_labelled_text(paragraph, label: str, body: str) -> None:
    """Preserve the template's bold-label + regular-body run pattern."""
    if not paragraph.runs:
        paragraph.add_run(label).bold = True
        paragraph.add_run(body)
        return
    paragraph.runs[0].text = label
    paragraph.runs[0].bold = True
    if len(paragraph.runs) == 1:
        paragraph.add_run(body)
    else:
        paragraph.runs[1].text = body
        paragraph.runs[1].bold = False
        for run in paragraph.runs[2:]:
            run.text = ""


def set_cell(cell, text: str) -> None:
    set_text(cell.paragraphs[0], text)
    for paragraph in cell.paragraphs[1:]:
        set_text(paragraph, "")


def update_arabic() -> None:
    doc = Document(AR_PATH)
    p = doc.paragraphs

    set_text(p[1], "ملف مشروع روبوت المحادثة")
    set_text(p[3], "مساعد كارماليت الرقمي للحجوزات وخدمة العملاء")
    set_text(p[4], "العميل: عيادات كارماليت الطبية")
    set_text(p[5], "إعداد: الشركة المركزية للتجارة الإلكترونية (جورمول)")
    set_text(p[6], "التاريخ: 2026-08-10")

    set_text(p[10], "عن روبوت محادثة كارماليت التفاعلي")
    set_text(
        p[11],
        "أعدّت جورمول مساعداً رقمياً ثنائي اللغة لعيادات كارماليت، يربط تجربة العميل "
        "بمعلومات العيادة المعتمدة ويساعده على اكتشاف الخدمات والأطباء وطلب المواعيد "
        "والوصول إلى فريق الاستقبال من خلال محادثة واضحة وآمنة.",
    )
    set_text(p[12], "يقدم روبوت المحادثة لكارماليت:")
    set_labelled_text(
        p[13],
        "معلومات موثوقة:",
        " إجابات بالعربية والإنجليزية عن خدمات كارماليت وأطبائها وموقعها ودوامها، "
        "بالاعتماد على قاعدة معرفة معتمدة وقابلة للتحديث.",
    )
    set_labelled_text(
        p[14],
        "الحجز والمواعيد:",
        " عرض الخدمات والأوقات العامة المتاحة وتسجيل طلبات المواعيد، مع دعم البحث "
        "عن الموعد وتغييره أو إلغائه بعد التحقق من بيانات العميل.",
    )
    set_labelled_text(
        p[15],
        "إرشاد آمن للخدمات:",
        " توجيه العميل نحو الاستشارة أو الطبيب المناسب دون تشخيص أو وصف علاج أو "
        "اختراع أسعار ونتائج ومواعيد أطباء غير معتمدة.",
    )
    set_labelled_text(
        p[16],
        "تكامل الرسائل القصيرة:",
        " ربط رسائل جورمول الخدمية برابط المحادثة، وإرسال إشعارات المواعيد والتأكيد "
        "والتغيير والإلغاء بعد تفعيل بوابة الرسائل واعتماد اسم المرسل.",
    )
    set_labelled_text(
        p[17],
        "السلامة والخصوصية:",
        " تصعيد الأسئلة الطبية والشكاوى وحالات ما بعد الإجراء، وجمع الحد الأدنى من "
        "بيانات التواصل مع حماية مسارات الإلغاء والمعلومات الحساسة.",
    )
    set_labelled_text(
        p[18],
        "لوحة الاستقبال:",
        " لوحة إدارية لمتابعة طلبات المواعيد والعملاء المحتملين والتصعيدات والإشعارات، "
        "وتحديث حالة كل طلب من مكان واحد.",
    )
    set_text(
        p[19],
        "يجمع حل كارماليت بين خدمة العملاء والحجز والمعلومات الطبية المسؤولة، ويهيئ "
        "رحلة متكاملة تبدأ من رسالة جورمول وتستمر حتى متابعة فريق الاستقبال.",
    )

    doc.core_properties.title = "ملف روبوت محادثة كارماليت"
    doc.core_properties.subject = "حل جورمول التفاعلي لعيادات كارماليت الطبية"
    doc.save(AR_PATH)


def update_english() -> None:
    doc = Document(EN_PATH)
    p = doc.paragraphs

    set_text(p[1], '"Turn Every Karmalite SMS into a Conversation"')
    set_text(p[2], "Introducing Karmalite’s Bilingual Patient-Service Chatbot")
    set_text(
        p[4],
        "“A safer, faster way to inform patients, explain services, request appointments, "
        "and connect with reception—directly from a JorMall SMS.”",
    )
    set_text(p[5], "Central E-Commerce Ltd. - JorMall | Prepared for Karmalite Medical Clinics")
    set_text(p[7], "A Digital Patient Journey for Karmalite")
    set_text(
        p[9],
        "JorMall has prepared a bilingual chatbot for Karmalite Medical Clinics that can be "
        "connected to Service SMS messages and the clinic’s digital customer journey.",
    )
    set_text(
        p[10],
        "Patients can open the chatbot from an SMS or web link, ask about Karmalite’s services "
        "and doctors, request an appointment, manage an existing request, receive location "
        "details, and reach the correct clinic team through a clear conversational interface.",
    )

    workflow = doc.tables[0]
    workflow_rows = [
        ("1", "Clinic content approval", "Karmalite validates its current doctors, services, contact details, hours, safety guidance, and operational policies."),
        ("2", "Configured Karmalite chatbot", "JorMall maintains the approved bilingual knowledge base, patient journey, appointment tools, and reception hand-off rules."),
        ("3", "JorMall SMS delivery", "A Karmalite Service SMS is sent to the intended patient or audience with a clear call to action and chatbot link."),
        ("4", "Patient interaction", "Patients ask questions, explore services, request appointments, manage bookings, and receive immediate Arabic or English guidance."),
        ("5", "Reception follow-up", "Appointment requests, leads, escalations, and notification records are available to the reception team through the admin dashboard."),
    ]
    for row, values in zip(workflow.rows[1:], workflow_rows):
        for cell, value in zip(row.cells, values):
            set_cell(cell, value)

    capability_text = [
        "Answer common questions about Karmalite’s services, doctors, location, and working hours.",
        "Explain treatments using approved information without inventing prices, schedules, or guaranteed results.",
        "Guide patients toward the relevant consultation while avoiding diagnosis, prescribing, or treatment selection.",
        "Collect qualified enquiries and structured appointment requests for reception follow-up.",
        "Help verified patients find, reschedule, or cancel appointment requests and receive location details.",
        "Communicate in Arabic or English and escalate medical, emergency, reception, or manager cases appropriately.",
    ]
    for paragraph, text in zip(p[13:19], capability_text):
        set_text(paragraph, text)

    benefits = doc.tables[1]
    benefit_rows = [
        ("More patient engagement", "Continue from a JorMall SMS into an interactive Karmalite conversation."),
        ("Faster bilingual answers", "Give patients immediate Arabic or English access to approved clinic information."),
        ("Safer medical communication", "Apply consistent medical boundaries and escalation rules."),
        ("More qualified appointments", "Collect complete requests after patients understand their options."),
        ("Reception efficiency", "Manage requests, leads, cancellations, and escalations in one dashboard."),
        ("Consistent clinic information", "Use one controlled source for clinic facts and guidance."),
    ]
    for row, values in zip(benefits.rows, benefit_rows):
        for cell, value in zip(row.cells, values):
            set_cell(cell, value)

    practical_uses = [
        ("Service discovery:", " explain Karmalite’s treatment and consultation categories."),
        ("Doctor routing:", " introduce the current team and record a preferred doctor."),
        ("Appointment management:", " request, find, reschedule, or cancel appointments securely."),
        ("Price enquiries:", " route unapproved prices to reception for a current quote."),
        ("Location and hours:", " provide approved contact, map, address, and hours."),
        ("Aftercare and escalation:", " route medical or urgent concerns safely."),
        ("Service SMS follow-up:", " connect appointment messages to the chatbot."),
    ]
    for paragraph, (label, body) in zip(p[22:29], practical_uses):
        set_labelled_text(paragraph, label, body)

    set_text(p[29], "Designed Around Karmalite")
    set_text(
        p[30],
        "The chatbot uses Karmalite’s bilingual clinic profile, current doctor team, service "
        "catalogue, appointment tools, reception dashboard, and safety rules.",
    )
    set_text(
        p[31],
        "Prices, doctor schedules, promotions, and detailed policies remain staff-confirmed "
        "until Karmalite supplies dated approvals.",
    )

    set_text(p[32], "Launch Readiness")
    readiness = [
        "Approve Karmalite’s clinic profile, services, doctors, contacts, and hours.",
        "Provide JorMall Service SMS test access and an approved sender ID.",
        "Confirm prices, doctor schedules, promotions, and appointment policies.",
        "Approve the bilingual safety, privacy, and escalation wording.",
        "Test SMS links, appointments, cancellations, delivery, and follow-up.",
    ]
    for paragraph, text in zip(p[33:38], readiness):
        set_text(paragraph, text)

    set_text(p[39], "Quotation for Karmalite Chatbot Service")
    set_text(
        p[40],
        "JorMall is pleased to submit the following commercial terms for the preparation and "
        "hosting of Karmalite’s customized bilingual chatbot.",
    )
    set_text(p[42], "Connect every Karmalite Service SMS to a useful, interactive patient journey.")
    set_text(
        p[43],
        "Contact your JorMall representative to approve the final content, activate Service SMS, "
        "and complete production launch testing.",
    )

    set_text(
        p[47],
        "JorMall is Jordan’s leading provider of Bulk and Service SMS solutions, serving sectors "
        "including healthcare, retail, automotive, banking, government, and telecommunications. "
        "For Karmalite, JorMall SMS can connect appointment communication and approved campaigns "
        "to the bilingual chatbot experience. Our SMS services offer:",
    )
    set_labelled_text(
        p[50],
        "Customized Communication:",
        " Arabic and English Service SMS content linked to Karmalite’s patient journey, "
        "appointment actions, and approved calls to action.",
    )
    set_text(
        p[54],
        "By combining JorMall Service SMS with Karmalite’s chatbot, the clinic can deliver timely "
        "patient communication, extend every message into an interactive journey, and support "
        "measurable reception follow-up.",
    )

    doc.core_properties.title = "Karmalite Chatbot Client Document"
    doc.core_properties.subject = "JorMall bilingual patient-service chatbot for Karmalite Medical Clinics"
    doc.save(EN_PATH)


if __name__ == "__main__":
    update_arabic()
    update_english()
    print(AR_PATH)
    print(EN_PATH)
