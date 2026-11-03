import json

from .language_helpers import normalize_output_language, localize_header


def run_optin_sms_campaign_generation(json_path, company_name, company_url, optin_sms_notes, optin_bitly_link, optin_phone_number,
                                      output_language=None, document_language=None, language=None):
    output_language = normalize_output_language(output_language, document_language, language)
    results = {
        "sms_type": "optin",
        "output_language": output_language,
        "document_language": output_language,
        "company_name": company_name,
        "company_url": company_url,
        "optin_sms_notes": optin_sms_notes,
        "optin_bitly_link": optin_bitly_link,
        "optin_phone_number": optin_phone_number,
        "analysis": {}
    }

    display_name = (company_name or "").rstrip()
    if display_name.endswith(" Jordan"):
        display_name = display_name[:-7].rstrip()

    notes_suffix_ar = f" - ملاحظات: {optin_sms_notes}" if optin_sms_notes and output_language == "ar" else ""
    notes_suffix_en = f" – Notes: {optin_sms_notes}" if optin_sms_notes and output_language != "ar" else ""

    if output_language == "ar":
        answers = {
            "رسالة إلغاء الاشتراك (بالعربية)" + notes_suffix_ar: (
                f"حضرة العميل، نود إعلامكم بأن رقم هاتفكم مشترك في خدمة الرسائل النصية التابعة لشركة {display_name}. "
                f"إذا أردتم إيقاف الرسائل، يرجى الضغط على الرابط أدناه.\n{optin_bitly_link}"
            ),
            "رسالة إلغاء الاشتراك (بالإنجليزية)": (
                f"Dear customer, your number is subscribed to the SMS service of {display_name}. "
                f"If you wish to stop receiving messages, please click the link below.\n{optin_bitly_link}"
            ),
        }
    else:
        answers = {
            "Arabic Opt-out SMS" + notes_suffix_en: (
                f"حضرة العميل، نرجو إعلامكم بأن رقم هاتفكم مشترك في خدمة الرسائل النصية التابعة لشركة {display_name}. "
                f"إذا أردت إيقاف الرسائل، اضغط على الرابط أدناه.\n{optin_bitly_link}"
            ),
            "English Opt-out SMS" + notes_suffix_en: (
                f"Dear customer, your number is subscribed to the SMS service of {display_name}. "
                f"If you wish to stop receiving messages, please click the link below.\n{optin_bitly_link}"
            )
        }

    for header, answer in answers.items():
        question = f"إنشاء رسالة إلغاء اشتراك لشركة {display_name} باستخدام رابط إلغاء الاشتراك." if output_language == "ar" else f"Generate {header.split(' – ')[0]} message for company {display_name} with opt-out link."
        result_header = localize_header(header) if output_language == "ar" else header
        results["analysis"][result_header] = {
            "header": result_header,
            "question": question,
            "answer": answer
        }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    return results
