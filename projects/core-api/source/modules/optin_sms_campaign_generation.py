import os
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv
import datetime
# ========================== #
#      INITIAL SETUP        #
# ========================== #


# ========================== #
#    MAIN ANALYSIS RUNNER   #
# ========================== #
import json

def run_optin_sms_campaign_generation(json_path, company_name, company_url, optin_sms_notes, optin_bitly_link, optin_phone_number):
    results = {
        "sms_type": "optin",
        "company_name": company_name,
        "company_url": company_url,
        "optin_sms_notes": optin_sms_notes,
        "optin_bitly_link": optin_bitly_link,
        "analysis": {}
    }

    # Remove " Jordan" from the end of the company name if it exists
    display_name = company_name.rstrip()
    if display_name.endswith(" Jordan"):
        display_name = display_name[:-7].rstrip()

    # Prepare suffix for header if notes exist
    notes_suffix = f" – Notes: {optin_sms_notes}" if optin_sms_notes else ""

    # Hardcoded answers
    answers = {
        "Arabic Opt-out SMS" + notes_suffix: (
            f""
            f"حضرة العميل، نرجو إعلامكم بأن رقم هاتفكم مشترك في خدمة الرسائل النصية التابعة لشركة {display_name}. "
            f"إذا أردت إيقاف الرسائل، اضغط على الرابط أدناه.\n{optin_bitly_link}"
        ),
        "English Opt-out SMS" + notes_suffix: (
            f""
            f"Dear customer, your number is subscribed to the SMS service of {display_name}. "
            f"If you wish to stop receiving messages, please click the link below.\n{optin_bitly_link}"
        )
    }

    # Iterate and store questions and answers
    for header, answer in answers.items():
        question = f"Generate {header.split(' – ')[0]} message for company {display_name} with opt-out link."
        print(f"⏳ Generating: {header}")
        print(question)

        results["analysis"][header] = {
            "header": header,
            "question": question,
            "answer": answer
        }

    # Save to file
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    return results
