"""Narrow answer selection from approved configuration; no model or retrieval changes."""
import re


def normalize(text):
    return re.sub(r'\s+', ' ', re.sub(r'[؟?!.،,]+$', '', text.strip().lower())).strip()


def ambiguous_question(text):
    return bool(re.fullmatch(r'(?:how much(?: is (?:it|that|this))?|what (?:is|about) (?:its|the) price|price|كم(?: سعره| سعرها| السعر| تكلفته| تكلفتها)?|بكم|شو سعره|ما سعره)', normalize(text)))


def clarification(text):
    return 'أي خدمة أو منتج تقصد؟' if re.search(r'[\u0600-\u06ff]',text) else 'Which service or product do you mean?'


def focused_config_answer(question, config):
    q=normalize(question);ar=bool(re.search(r'[\u0600-\u06ff]',q))
    # A single contact field request, not another company's address or a compound query.
    email=re.fullmatch(r'(?:(?:what is|what\x27s|give me|please give me) )?(?:the |your )?(?:contact )?e-?mail(?: address)?(?: for (?:jormall|jor mall|your company))?',q)
    email_ar=re.fullmatch(r'(?:ما |ما هو |أعطني |اعطني )?(?:البريد (?:الإلكتروني|الالكتروني)|بريدكم (?:الإلكتروني|الالكتروني)|الإيميل|الايميل)(?: للتواصل)?(?: مع (?:جورمول|جور مول|jormall))?',q)
    if email or email_ar:
        details=getattr(config,'contact_details',{}) or {}
        value=details.get('email','') or next(iter(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', config.contact_info or '')), '')
        if value:return ('البريد الإلكتروني: ' if ar else 'Email: ')+value, 'contact_info'
        return ('لا يتوفر بريد إلكتروني ضمن المعلومات المعتمدة.' if ar else 'No email address is available in the approved information.'), 'contact_info'
    # Require an explicit chatbot/campaign target for these additional variants.
    time_request=(re.fullmatch(r'\bhow long does it take to (?:create|set up|build) (?:the |a |your )?(?:interactive )?(?:campaign )?chatbot\b',q)
        or re.fullmatch(r'(?:كم يستغرق|كم تستغرق|ما مدة) (?:إنشاء|انشاء|إعداد|اعداد) (?:شات بوت|الشات بوت)(?: الحملة)?',q))
    if time_request:
        value=(config.campaign_creation_process_ar if ar else config.campaign_creation_process_en).strip()
        if not value:return None
        # Keep the actual approved sentence including prerequisites, not a synthesized deadline.
        sentences=re.split(r'(?<=[.!])\s+',value)
        chosen=next((s for s in sentences if ('تستغرق' in s if ar else s.startswith('Creation takes'))),value)
        return chosen,'campaign_creation_process'
    if config.client_slug == 'central-e-commerce-co-ltd' and re.fullmatch(
        r'(?:what are (?:the )?(?:chatbot )?hosting packages(?: and prices)?|ما (?:أسعار|اسعار) باقات (?:استضافة الشات بوت|الاستضافة))', q):
        # Reuse the existing approved, baseline-validated pricing values.
        from app.answers.safety import chatbot_hosting_packages_text_en, chatbot_hosting_packages_text_ar
        if ar:
            return 'باقات الاستضافة بعد الشهر المشمول: ' + chatbot_hosting_packages_text_ar() + '.', 'campaign_offer_details'
        return 'Hosting after the included month: ' + chatbot_hosting_packages_text_en() + '.', 'campaign_offer_details'
    return None
