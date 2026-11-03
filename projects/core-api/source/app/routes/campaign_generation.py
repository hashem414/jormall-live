from flask import Blueprint, request, jsonify, session, send_from_directory

campaign_bp = Blueprint("campaign", __name__)

import os
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))

GENERATED_DIR = os.path.join(BASE_DIR, "app", "generated")
JSON_DIR = os.path.join(GENERATED_DIR, "json")
DOCX_DIR = os.path.join(GENERATED_DIR, "docx")

os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(DOCX_DIR, exist_ok=True)

from uuid import uuid4
import os
from flask import request, jsonify, session

from modules.generate_ai_docx_with_markdown import generate_ai_docx
from modules.smart_sms_campaign_generation import run_smart_sms_campaign_generation
from modules.chain_sms_campaign_generation import run_chain_sms_campaign_generation
from modules.premium_sms_campaign_generation import run_premium_sms_campaign_generation
from modules.personalized_sms_campaign_generation import run_personalized_sms_campaign_generation
from modules.lead_sms_campaign_generation import run_lead_sms_campaign_generation
from modules.optin_sms_campaign_generation import run_optin_sms_campaign_generation


@campaign_bp.route("/generate-campaign", methods=["POST"])
def generate_campaign():
    data = request.get_json() or {}

    # Raw incoming value from Flutter
    raw_sms_type = (data.get("smsType") or "").strip().lower()

    # Normalize Flutter/UI labels to backend keys
    sms_type_map = {
        "smart reach": "smart",
        "smart": "smart",
        "chain sms": "chain",
        "chain": "chain",
        "premium sms": "premium",
        "premium": "premium",
        "personalized sms": "personalized",
        "personalized": "personalized",
        "lead sms": "lead",
        "lead": "lead",
        "opt-in sms": "optin",
        "opt in sms": "optin",
        "optin sms": "optin",
        "optin": "optin",
    }

    sms_type = sms_type_map.get(raw_sms_type, raw_sms_type)

    # Mandatory fields
    company_name = (data.get("companyName") or "").strip()
    company_url = (data.get("companyURL") or "").strip()
    campaign_brief = (data.get("campaignBrief") or "").strip()

    # Optional fields
    bitly_link = (data.get("bitlyLink") or "").strip()
    phone_number = (data.get("phoneNumber") or "").strip()
    cities = (data.get("cities") or "").strip()
    amman_direction = (data.get("ammanDirection") or "").strip()
    delivery_date = (data.get("deliveryDate") or "").strip()

    # Chain SMS fields
    chain_messages = data.get("chainMessages", []) or []
    chain_delivery_dates = [msg.get("date", "") for msg in chain_messages]
    chain_delivery_times = [msg.get("time", "") for msg in chain_messages]
    chain_campaign_title = (data.get("chainCampaignTitle") or "").strip()

    # Opt-In fields
    optin_sms_notes = (data.get("optinSMSNotes") or "").strip()
    optin_bitly_link = (data.get("optinBitlyLink") or "").strip()
    optin_phone_number = (data.get("optinPhoneNumber") or "").strip()

    if not company_name or not company_url:
        return jsonify({
            "ok": False,
            "error": "Missing required fields (Company Name or URL)."
        }), 400

    try:
        campaign_id = str(uuid4())
        json_path = os.path.join(JSON_DIR, f"{campaign_id}_analysis.json")

        if sms_type == "smart":
            run_smart_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                campaign_brief=campaign_brief,
                bitly_link=bitly_link,
                phone_number=phone_number,
                cities=cities,
                amman_direction=amman_direction,
                delivery_date=delivery_date,
            )

        elif sms_type == "chain":
            run_chain_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                chain_campaign_title=chain_campaign_title,
                company_url=company_url,
                campaign_brief=campaign_brief,
                chain_messages=chain_messages,
                chain_delivery_dates=chain_delivery_dates,
                chain_delivery_times=chain_delivery_times,
                cities=cities,
                amman_direction=amman_direction,
            )

        elif sms_type == "premium":
            run_premium_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                campaign_brief=campaign_brief,
            )

        elif sms_type == "personalized":
            run_personalized_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                campaign_brief=campaign_brief,
                bitly_link=bitly_link,
                phone_number=phone_number,
                cities=cities,
                amman_direction=amman_direction,
                delivery_date=delivery_date,
            )

        elif sms_type == "lead":
            run_lead_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
            )

        elif sms_type == "optin":
            run_optin_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                optin_sms_notes=optin_sms_notes,
                optin_bitly_link=optin_bitly_link,
                optin_phone_number=optin_phone_number,
            )

        else:
            return jsonify({
                "ok": False,
                "error": f"Invalid SMS type: {raw_sms_type}"
            }), 400

        # Generate DOCX
        filename = generate_ai_docx(campaign_id, json_path)

        if not filename or not os.path.exists(filename):
            return jsonify({
                "ok": False,
                "error": "DOCX file was not created."
            }), 500

        # Public URL for browser/download
        docx_url = f"/exports/docx/{os.path.basename(filename)}"

        # log_admin_activity(
        #     username=session.get("username", "unknown"),
        #     action=f"generate campaign ({sms_type})",
        #     filename=filename,
        # )

        return jsonify({
            "ok": True,
            "manualDocxUrl": docx_url,
            "manualDocxPath": filename,
            "fileName": os.path.basename(filename),
            "smsType": sms_type,
        }), 200

    except Exception as e:
        print("❌ Campaign generation error:", str(e))
        return jsonify({
            "ok": False,
            "error": f"Failed to generate campaign: {str(e)}"
        }), 500
    
from flask import send_from_directory

@campaign_bp.route("/exports/docx/<filename>")
def exported_docx(filename):
    return send_from_directory(DOCX_DIR, filename)