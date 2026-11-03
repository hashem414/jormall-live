import smtplib
from email.message import EmailMessage
import os
from flask import Blueprint, request, jsonify

email_bp = Blueprint("email", __name__)

@email_bp.post("/send-email")
def send_email():
    data = request.get_json(force=True)

    to_email = data.get("to")
    subject = data.get("subject", "")
    body = data.get("body", "")
    attachment_path = data.get("attachment_path")

    if not to_email or not subject or not body:
        return jsonify({"ok": False, "msg": "Missing required fields"}), 400

    SMTP_HOST = (os.environ.get("SMTP_HOST") or "").strip()
    SMTP_PORT = int((os.environ.get("SMTP_PORT") or "587").strip())
    SMTP_USER = (os.environ.get("SMTP_USER") or "").strip()
    SMTP_PASS = (os.environ.get("SMTP_PASS") or "").strip()
    FROM_EMAIL = (os.environ.get("FROM_EMAIL") or SMTP_USER).strip()

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        return jsonify({"ok": False, "msg": "SMTP not configured"}), 500

    try:
        msg = EmailMessage()
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        if body.strip().lower().startswith("<html"):
            msg.set_content("This email contains HTML content. Please view it in an HTML-compatible email client.")
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)

        if attachment_path:
            if not os.path.exists(attachment_path):
                return jsonify({
                    "ok": False,
                    "msg": f"Attachment not found: {attachment_path}"
                }), 400

            filename = os.path.basename(attachment_path)
            with open(attachment_path, "rb") as f:
                file_data = f.read()

            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=filename
            )

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)

        return jsonify({"ok": True, "msg": "Email sent"}), 200

    except Exception as e:
        return jsonify({"ok": False, "msg": f"Send failed: {str(e)}"}), 500