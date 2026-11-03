"""
إرسال البريد عبر SMTP — بيستخدم مكتبة بايثون القياسية، بدون اعتماديات جديدة.

بينشّط لحاله لما `SMTP_HOST` ينتعبّى بـ .env. إذا مش معبّى، `is_configured()`
بترجّع False والنظام بيكمل بدون تحقق (مع تحذير) — عيادة شغّالة ما بتنكسر
لأن إعداد البريد ناقص.
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from .config import get_settings

logger = logging.getLogger(__name__)

# تحقّق شكلي بسيط — الغرض إمساك الأخطاء المطبعية، مش التحقق من وجود العنوان.
# الوجود الحقيقي بيثبت لما يوصل الرمز ويرجّعه العميل.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def is_valid_email(value: str) -> bool:
    value = (value or "").strip()
    return bool(value) and len(value) <= 254 and bool(_EMAIL_RE.match(value))


def normalize_email(value: str) -> str:
    """الإيميل غير حساس لحالة الأحرف عملياً — بنخزّنه ونطابقه بحروف صغيرة."""
    return (value or "").strip().lower()


def is_configured() -> bool:
    return bool(get_settings().smtp_host)


def configuration_status() -> dict:
    settings = get_settings()
    return {
        "configured": is_configured(),
        "host": settings.smtp_host or None,
        "port": settings.smtp_port,
        "from": settings.mail_from or settings.smtp_user or None,
        "starttls": settings.smtp_starttls,
    }


def send_email(to: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    """
    بيرمي استثناء عند الفشل — الطبقة اللي فوق بتقرر شو تعمل.
    ما بنبلع الخطأ هون: رمز ما انبعت لازم يوقف الحجز، مش يمرّ بصمت.
    """
    settings = get_settings()
    if not is_configured():
        raise RuntimeError("SMTP غير مهيأ — عبّي SMTP_HOST بملف .env")

    sender = settings.mail_from or settings.smtp_user
    if not sender:
        raise RuntimeError("MAIL_FROM أو SMTP_USER لازم يكون معبّى")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.mail_from_name, sender))
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    timeout = settings.smtp_timeout_seconds
    password = settings.smtp_password.get_secret_value()

    if settings.smtp_port == 465:                     # SSL مباشر
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                              timeout=timeout, context=ssl.create_default_context()) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
            smtp.ehlo()
            if settings.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, password)
            smtp.send_message(msg)

    logger.info("إيميل انبعت إلى %s — %s", to, subject)


# ======================================================================
# قالب رمز التحقق
# ======================================================================
_SUBJECT = {
    "ar": "رمز تأكيد موعدك — عيادة كارماليت",
    "en": "Your appointment verification code — Karmalite Clinic",
}


def verification_bodies(code: str, lang: str, ttl_minutes: int) -> tuple[str, str]:
    """بيرجّع (نص عادي، HTML) — بعض عملاء البريد ما بيعرضوا HTML."""
    if lang == "en":
        text = (
            f"Your Karmalite verification code is: {code}\n\n"
            f"Enter it in the chat to confirm your appointment request.\n"
            f"The code expires in {ttl_minutes} minutes.\n\n"
            "If you did not request an appointment, you can ignore this email."
        )
    else:
        text = (
            f"رمز التحقق الخاص فيك بعيادة كارماليت هو: {code}\n\n"
            f"اكتبه بالمحادثة لتأكيد طلب موعدك.\n"
            f"الرمز بينتهي بعد {ttl_minutes} دقيقة.\n\n"
            "إذا ما طلبت موعداً، بتقدر تتجاهل هالرسالة."
        )

    direction = "ltr" if lang == "en" else "rtl"
    html = f"""<div dir="{direction}" style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
     background:#f3f5f4;padding:28px;color:#283736">
  <div style="max-width:460px;margin:0 auto;background:#fff;border:1px solid #dfe1e0;
       border-radius:16px;padding:26px">
    <h2 style="margin:0 0 14px;font-size:17px;color:#4d6160">
      {'Karmalite Clinic' if lang == 'en' else 'عيادة كارماليت'}
    </h2>
    <p style="margin:0 0 18px;font-size:14px;line-height:1.7">
      {'Your verification code is:' if lang == 'en' else 'رمز التحقق الخاص فيك هو:'}
    </p>
    <div style="font-size:30px;font-weight:700;letter-spacing:7px;color:#4d6160;
         background:#f3f5f4;border-radius:12px;padding:14px;text-align:center;
         font-family:ui-monospace,Menlo,Consolas,monospace">{code}</div>
    <p style="margin:18px 0 0;font-size:12.5px;line-height:1.7;color:#707473">
      {f'The code expires in {ttl_minutes} minutes.' if lang == 'en'
       else f'الرمز بينتهي بعد {ttl_minutes} دقيقة.'}<br>
      {'If you did not request an appointment, you can ignore this email.' if lang == 'en'
       else 'إذا ما طلبت موعداً، بتقدر تتجاهل هالرسالة.'}
    </p>
  </div>
</div>"""
    return text, html


def send_verification_code(to: str, code: str, lang: str = "ar") -> None:
    ttl = get_settings().email_code_ttl_minutes
    text, html = verification_bodies(code, lang, ttl)
    send_email(to, _SUBJECT.get(lang, _SUBJECT["ar"]), text, html)
