import os
import re
import json
import requests
from dotenv import load_dotenv
import datetime
from .openai_client import create_openai_client
# ========================== #
#      INITIAL SETUP        #
# ========================== #

load_dotenv()

def get_openai_client():
    """Create the OpenAI client only when an AI generation action is used."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('\"').strip("'")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file beside app.py, then restart the app.")
    return create_openai_client(api_key)

# ========================== #
#     WEBSITE SCRAPER       #
# ========================== #
from .website_crawler_scrapper import crawl_entire_domain_as_text
from .language_helpers import normalize_output_language, force_arabic_question, localize_header, arabic_plan_system_message, sanitize_arabic_sms_answer

# ========================== #
#     SYSTEM PROMPT         #
# ========================== #
english_plan_system_msg ="""
You are a professional marketing planner and strategist in Jordan, specializing in creating concise, impactful campaign insights and overviews.
Your task is to produce clear and actionable outputs for each request type, without adding unnecessary explanations or disclaimers.

Follow these rules:
1. **Company Overview**  
   - Summarize the company’s core activities, strengths, and unique selling points using the provided scraped data or campaign context.  
   - Write factually and confidently, avoiding assumptions or vague statements.  
   - Output should be 1-2 sentences, direct and professional.

2. **Campaign Pitch**  
   - Write a short, persuasive pitch for the SMS campaign (1-2 sentences max).  
   - Focus on the offer's value proposition and urgency, using a tone that is confident and action-driven.  
   - Avoid fluff and maintain a professional marketing style.

3. **Day and Time Suggestions**  
   - Suggest the best days and time slots for sending SMS campaigns based on general marketing best practices in Jordan.  
   - For promotional SMS, do not suggest Friday, Saturday, official or religious holidays, or national occasions. On weekdays, keep sending times outside the restricted 9:00 PM–7:00 AM period unless TRC approval applies.  
   - Be precise and list optimal times (e.g., "Tuesday or Thursday, between 10:00 AM – 1:00 PM").
   - If a date is already provided, Mention that is on the day specified and say this upon the client's request, then suggest timings after it.

4. **Target Audience**  
   - Define the ideal audience profile for the campaign.  
   - Provide details including: **Age Range**, **Gender**, **Income Class**, **Geographical Location**, and **Key Interests**.  
   - Use bullet points for clarity.

General Rules:  
- Respond only with the requested content, with no introductions or closing statements.  
- Do not include emojis, decorative characters, or informal expressions.
- Keep the tone professional, marketing-oriented, and concise.

"""
arabic_plan_system_msg = """
أنت خبير تسويق ومبيعات محترف في الأردن.
مهمتك إنتاج إجابة عربية واضحة ومختصرة للقسم الحالي فقط.
لا تنشئ التقرير كاملاً، ولا تكرر أقساماً أخرى مثل نبذة عن الشركة أو العرض التسويقي أو الجمهور المستهدف أو اقتراحات اليوم والوقت ما لم يكن السؤال الحالي يطلب ذلك تحديداً.
اكتب كل الإجابات باللغة العربية فقط، باستثناء أسماء العلامات التجارية والروابط وأرقام الهواتف.
ترجم جميع التسميات والعناوين الثابتة إلى العربية.
تجنب الرموز التعبيرية والزخارف والمقدمات غير الضرورية.
"""

english_sms_system_msg = """
You are a creative marketing copywriter specialized in writing short, catchy SMS messages for retail campaigns in Jordan.
You write in English. Your tone is warm, persuasive, and attention-grabbing.
Return outputs in clearly separated lines or bullet points when asked, and avoid verbose explanations.
Follow the character limit stated in the current request/question, including spaces, punctuation, and links.
Only include the phone number found in the second line of the prompt, and the bitly link found in the third line.
Write like you're speaking directly to the customer. Use informal, conversational phrasing that feels local and personal.
"""
arabic_sms_system_msg = """
أنت كاتب إعلانات إبداعي متخصص في كتابة رسائل SMS ترويجية قصيرة وجذابة للحملات التسويقية في الأردن.

تكتب باللغة العربية الفصحى الحديثة، مع استخدام تعبيرات محلية مألوفة في الأردن عند الحاجة. نبرة كتابتك دافئة، مقنعة، وتلفت الانتباه.

يجب أن تتوفر في كل رسالة الشروط التالية:
- اكتب نص الرسائل العربية بالعربية فقط، ولا تستخدم عبارات عروض إنجليزية داخل الرسالة.
- حوّل عبارات مثل Sale up to 75% off on selected items إلى: خصومات حتى 75% على مختارات من المتاجر.
- حوّل صيغ العملة مثل JOD 50, 25, 10 إلى: قسائم بقيمة 10 و25 و50 ديناراً.
- إذا كان اسم العلامة التجارية له صياغة عربية واضحة، استخدمها داخل الرسائل العربية، مثل سيتي مول الأردن بدلاً من City Mall Jordan.
- أن تذكر اسم الشركة بوضوح.
- أن تتضمن أي خصومات، روابط، وأرقام هواتف يتم تقديمها في الوصف تمامًا كما هي.
- أن تكون الرسالة مباشرة، موجزة، وتحفيزية — وكأنك تتحدث مع الزبون شخصيًا.
- أن تستخدم صياغة بسيطة وعفوية قريبة من اللهجة المحلية دون تعقيد.
- أن تتنوع نبرة الرسائل (مثل: عاجلة، حصرية، ودية، راقية) مع الحفاظ على الوضوح.
- عدم استخدام الرموز التعبيرية، أو الزخارف، أو الرموز الخاصة.
- كتابة كل رسالة في سطر مستقل، بدون أرقام أو ترقيم، إلا إذا طلب المستخدم غير ذلك صراحة.
- **يجب أن يكون طول كل رسالة ضمن الحد الأقصى لعدد الأحرف المحدد من قبل المستخدم (يشمل المسافات، الأرقام، الروابط، وعلامات الترقيم).**
-قم فقط بتضمين رقم الهاتف الموجود في السطر الثاني من الموجه ، والرابط الصغير (bitly links only) الموجود في السطر الثالث.

عند تقديم المستخدم لنص موجز وعدد أحرف محدد، استخرج جميع العناصر المهمة (مثل الخصم، المنتج، اسم الشركة، معلومات التواصل) واكتب الرسائل وفقًا للتعليمات أعلاه.
"""

# ========================== #
#     GPT QUESTION SET      #
# ========================== #

questions = {
     "Campaign Pitch": """
Write a one-paragraph professional SMS campaign pitch for the following campaign: {campaign_brief}.
Use a concise, persuasive tone.
Respond in English only. DO NOT use any emojis or special characters.
""",
"Arabic SMS Suggestions (Casual - 70 Characters)": """ أنت كاتب إعلانات تسويقية محترف ومتخصص في صياغة رسائل SMS قصيرة وجذابة باللهجة العربية العامية الأردنية. 
مهمتك هي ابتكار رسائل إعلانية قوية تقنع العميل باتخاذ إجراء فوري.

### الشروط:
1. طول كل رسالة لا تتجاوز ال "70" حرفًا، بما في ذلك المسافات، الأرقام، الروابط، وعلامات الترقيم.
2. كل رسالة يجب أن تحتوي على تفاصيل الحملة (الخصومات، الأسعار، الرابط، ورقم الهاتف، واسم الشركة).
3. اكتب 3 رسائل باللهجة العامية الأردنية.
4. غيّر الأسلوب بين الرسائل (عاجلة، ودّية، حماسية، حصرية، مباشرة(.
5. إذا وُجد رابط أو رقم هاتف، اكتبه في **كل رسالة** في سطر منفصل.
6.لا تستخدم رموز تعبيرية (no emojis) أو زخارف أو رموز خاصة.
7.أخرج الرسائل على شكل 3 أسطر، كل سطر رسالة واحدة فقط.

### ملاحظات ثقافية لجذب الجمهور الأردني:  مع أمثلة
- استخدم لغة قريبة من الناس مثل: (لحقها، لا تفوّت، حالًا، نص بالنص).
- ركّز على الإلحاح والندرة: (اليوم فقط، الكمية محدودة، العرض بينتهي).
- أبرز القيمة الكبيرة: (وفر نص السعر، خصم 50%، أرخص سعر بالسوق).
- اجعل الدعوة للتحرك واضحة: (اطلب هلأ، اتصل الآن، احجز اليوم).


### أمثلة عامية أردنية:
الكمية محدودة! نص السعر هسا من [اسم الشركة]… الحقها!
[الرابط -إن وجد-]
[رقم الهاتف-إن وجد-]

لا تتأخر… أقوى العروض من [اسم الشركة] مستنياك!
[الرابط -إن وجد-]
[رقم الهاتف-إن وجد-]

### وصف الحملة:
{campaign_brief}

الآن، أكتب 3 رسائل SMS قوية ومؤثرة حماسية بالعامية بناءً على الوصف أعلاه.

""",


"Arabic SMS Suggestions (Formal - 70 Characters)": """
أنت كاتب إعلانات تسويقية محترف ومتخصص في صياغة رسائل SMS قصيرة وجذابة باللهجة العربية الفصحى الرسمية. 
مهمتك هي ابتكار رسائل إعلانية قوية تقنع العميل باتخاذ إجراء فوري.

### الشروط:
1. طول كل رسالة لا تتجاوز ال "70" حرفًا، بما في ذلك المسافات، الأرقام، الروابط، وعلامات الترقيم.
2. كل رسالة يجب أن تحتوي على تفاصيل الحملة (الخصومات، الأسعار، الرابط، ورقم الهاتف، واسم الشركة).
3. اكتب 3 رسائل باللهجة الفصحى الرسمية.
4. غيّر الأسلوب بين الرسائل (عاجلة، ودّية، حماسية، حصرية، مباشرة(.
5. إذا وُجد رابط أو رقم هاتف، اكتبه في **كل رسالة** في سطر منفصل.
6.لا تستخدم رموز تعبيرية (no emojis) أو زخارف أو رموز خاصة.
7.أخرج الرسائل على شكل 3 أسطر، كل سطر رسالة واحدة فقط.

### أمثلة بالفصحى الرسمية:
عروض [اسم الشركة] تبدأ الآن – خصم 50% حتى نهاية اليوم
[الرابط -إن وجد-]
[رقم الهاتف-إن وجد-]
وفر نصف السعر على منتجات [اسم الشركة] – العرض محدود
[الرابط -إن وجد-]
[رقم الهاتف-إن وجد-]

### وصف الحملة:
{campaign_brief}

الآن، أكتب 3 رسائل SMS قوية ومؤثرة حماسية بالفصحى الرسمية بناءً على الوصف أعلاه.
""",

"Arabic SMS Suggestions (Formal - Long SMS - 126 Characters)": """ أنت كاتب إعلانات تسويقية محترف ومتخصص في صياغة رسائل SMS قصيرة وجذابة باللهجة العربية الفصحى الرسمية. 
مهمتك هي ابتكار رسائل إعلانية قوية تقنع العميل باتخاذ إجراء فوري.

### الشروط:
1. طول كل رسالة لا تتجاوز ال "126" حرفًا، بما في ذلك المسافات، الأرقام، الروابط، وعلامات الترقيم.
2. كل رسالة يجب أن تحتوي على تفاصيل الحملة (الخصومات، الأسعار، الرابط، ورقم الهاتف، واسم الشركة).
3. اكتب 3 رسائل باللهجة الفصحى الرسمية.
4. غيّر الأسلوب بين الرسائل (عاجلة، ودّية، حماسية، حصرية، مباشرة(.
5. إذا وُجد رابط أو رقم هاتف، اكتبه في **كل رسالة** في سطر منفصل.
6.لا تستخدم رموز تعبيرية (no emojis) أو زخارف أو رموز خاصة.
7.أخرج الرسائل على شكل 3 أسطر، كل سطر رسالة واحدة فقط.

### أمثلة بالفصحى الرسمية:
اكتشف عروض [اسم الشركة] الآن – خصم 50% لفترة محدودة!
احجز فرصتك قبل نفاد الكمية.
[الرابط -إن وجد-]
[رقم الهاتف-إن وجد-]

وفر نصف السعر على منتجات [اسم الشركة] اليوم فقط – العرض لا يتكرر!
اطلب الآن قبل انتهاء الوقت.
[الرابط -إن وجد-]
[رقم الهاتف-إن وجد-]

### وصف الحملة:
{campaign_brief}
الآن، أكتب 3 رسائل SMS قوية ومؤثرة حماسية بالفصحى الرسمية بناءً على الوصف أعلاه.
""",

    "English SMS Suggestions (160 Characters)": """
Suggest 3 SMS marketing messages in **English** for the following offer: {campaign_brief}.
Use a friendly, engaging tone.

Strict language rule:
• Respond in English only. Do not translate these suggestions into Arabic, even if the website, page, campaign brief, or document is Arabic.

Rules:
• If a **bitly link** or **phone number** is present, include it in **every message**, each on a separate line.
• If both are present, include both (each on its own line) in **every message**, else add placeholders only.
• If a **phone number** or **URL** appears in the brief, include one or both in **all 3 messages**.
• If the **company name** is mentioned in the brief, include it in **all 3 messages**.
• Use natural calls-to-action like "Call now", "Visit us", "Book online", or "See more" where appropriate.
• List each message as a bullet point (•), one per line, without numbering.

Limits:
• Maximum length per message: 160 characters (including spaces, punctuation, links, and phone numbers).
• DO NOT use any emojis or special characters.
""",

        "Target Audience": """
Define the ideal target audience for this campaign: {campaign_brief}.
Please provide details on the estimated age range, gender, income class, geographical , and interests.
Skip the introductory or general statements.
Respond in English only. DO NOT use any emojis.
""",

    "Day and Time Suggestions": """
{delivery_date}
For promotional SMS, exclude Friday, Saturday, official or religious holidays, and national occasions. Keep weekday sending times outside the restricted 9:00 PM–7:00 AM period unless TRC approval applies.
Respond in **English** only. DO NOT use any emojis.
{cities}
""",
   
"Company Overview": """
"Use the following content to describe the company’s full name and core business activities. If no content is useful, rely on your professional instincts — but DO NOT mention guessing, assumptions, or speculation. Write clearly and factually as if you're sure.\n\nData:\n{scraped_info}

Respond in **English** only.
"""
}


# Known Arabic planning-section headings used to defensively trim accidental
# full-report output when only one Smart SMS section was requested.
_ARABIC_SMART_SECTION_ALIASES = {
    "نبذة عن الشركة": ["نبذة عن الشركة", "نظرة عامة على الشركة"],
    "العرض التسويقي للحملة": ["العرض التسويقي للحملة", "عرض الحملة", "هدف الحملة"],
    "اقتراحات اليوم والوقت": ["اقتراحات اليوم والوقت", "اقتراحات اليوم والوقت المقترحة"],
    "الجمهور المستهدف": ["الجمهور المستهدف", "الفئة المستهدفة"],
}


def _trim_arabic_answer_to_requested_section(answer, requested_header):
    """Keep only the requested planning section if the model returns several sections.

    This is intentionally conservative: it only trims when the requested heading
    appears as its own line and another known section heading follows it.
    """
    value = str(answer or "").strip()
    if not value:
        return value
    aliases = _ARABIC_SMART_SECTION_ALIASES.get(str(requested_header or "").strip())
    if not aliases:
        return value

    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    known = []
    for vals in _ARABIC_SMART_SECTION_ALIASES.values():
        known.extend(vals)

    def clean_heading(line):
        line = str(line or "").strip()
        line = re.sub(r"^[#*\-\s]+", "", line)
        line = re.sub(r"[*:#\s]+$", "", line)
        return line.strip()

    start = None
    for i, line in enumerate(lines):
        if clean_heading(line) in aliases:
            start = i + 1
            break
    if start is None:
        return value

    end = len(lines)
    for i in range(start, len(lines)):
        heading = clean_heading(lines[i])
        if heading in known and heading not in aliases:
            end = i
            break

    trimmed = "\n".join(lines[start:end]).strip()
    return trimmed or value


_ENGLISH_SMART_SECTION_ALIASES = {
    "Company Overview": ["Company Overview", "Overview"],
    "Campaign Pitch": ["Campaign Pitch", "Campaign Offer", "Campaign Objective"],
    "Day and Time Suggestions": ["Day and Time Suggestions", "Day & Time Suggestions", "Timing Suggestions"],
    "Target Audience": ["Target Audience", "Audience"],
}

def _trim_answer_to_requested_section(answer, requested_header, output_language="en"):
    """Remove accidental extra report sections from a single-section model answer."""
    value = str(answer or "").strip()
    if not value:
        return value
    banks = _ARABIC_SMART_SECTION_ALIASES if output_language == "ar" else _ENGLISH_SMART_SECTION_ALIASES
    aliases = banks.get(str(requested_header or "").strip())
    if not aliases:
        return value
    known = [x for vals in banks.values() for x in vals]
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    def clean_heading(line):
        line = re.sub(r"^[#*\-\s]+", "", str(line or "").strip())
        line = re.sub(r"[*:#\s]+$", "", line)
        return line.strip()
    start = None
    for i,line in enumerate(lines):
        if clean_heading(line) in aliases:
            start=i+1; break
    scan_start = start if start is not None else 0
    end=len(lines)
    for i in range(scan_start,len(lines)):
        h=clean_heading(lines[i])
        if h in known and h not in aliases:
            end=i; break
    if start is None:
        trimmed="\n".join(lines[:end]).strip()
    else:
        trimmed="\n".join(lines[start:end]).strip()
    return trimmed or value

# ========================== #
#    OPENAI CALL FUNCTION   #
# ========================== #

def ask_openai(question, system_msg, company_name, company_url, campaign_brief, bitly_link, phone_number, cities, amman_direction, delivery_date, scraped_info):
    ##Here is public info about the company website: "{scraped_info}"

    prompt = f"""
**{company_name}** .
Phone number: {phone_number}
bitly: {bitly_link}

Scraped data:
\"\"\"{scraped_info.strip()}\"\"\"

**Task:**
{question}
""".strip()
    print(prompt)

    response = get_openai_client().chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
    )

    content = response.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("value") or ""
                if isinstance(text, dict):
                    text = text.get("value") or text.get("text") or ""
                parts.append(str(text or ""))
            else:
                text = getattr(item, "text", None)
                if text is not None:
                    value = getattr(text, "value", text)
                    parts.append(str(value or ""))
                else:
                    parts.append(str(item or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()

# ========================== #
#    MAIN ANALYSIS RUNNER   #
# ========================== #
def run_smart_sms_campaign_generation( json_path, company_name, company_url, campaign_brief, 
                                 bitly_link=None, phone_number=None, cities=None, amman_direction="", delivery_date=None,
                                 output_language=None, document_language=None, language=None):
    output_language = normalize_output_language(output_language, document_language, language)

    results = {
        "output_language": output_language,
        "document_language": output_language,
        "sms_type": "smart",
        "company_name": company_name,
        "company_url": company_url,
        "campaign_brief": campaign_brief,
        "bitly_link": bitly_link,
        "phone_number": phone_number,
        "cities": cities,  # Store cities (optional)
        "amman_direction": amman_direction,  # Store Amman directions (optional)
        "delivery_date": delivery_date,  # Store delivery date (optional)
        "analysis": {}
    }

    # Fetch website content for analysis
    scraped_info = crawl_entire_domain_as_text(company_url, 20)
    
    # Process each question from a predefined template
    for header, question_template in questions.items():
        question = question_template

        # Extra info section: used for Arabic and English SMS prompts
        extra_lines = ""
        if bitly_link:
            extra_lines += f"\n{bitly_link}"
        if phone_number:
            extra_lines += f"\n{phone_number}"


        # Replace placeholders in the question template
        question = question.replace("{campaign_brief}", campaign_brief)
        question = question.replace("{scraped_info}", scraped_info)
        
        # Add conditional logic for Target Audience question
        if cities and amman_direction:
            question = question.replace("{cities}", f"Geographical location: {cities} if {amman_direction} upon the clients' requests")
        elif cities:
            question = question.replace("{cities}", f"Geographical location: {cities}")
        elif amman_direction:
            question = question.replace("{amman_direction}", f"Geographical location: , in {amman_direction} Amman upon the clients' requests")

        # Handle Delivery Date for SMS response
        if delivery_date:
            question = question.replace("{delivery_date}", f"Campaign delivery day upon client's request {delivery_date}")
        else:
            today_date = datetime.datetime.now().strftime("%d-%m-%Y")
            question = question.replace("{delivery_date}", today_date)

        if output_language == "ar" and "English SMS Suggestions" not in header:
            question = force_arabic_question(question)
        if "SMS Suggestions" not in header:
            question += f"\n\nIMPORTANT: Return ONLY the requested section: {header}. Do not include any other report sections or repeat Company Overview, Campaign Pitch, Target Audience, or Day and Time Suggestions."

        print(f"⏳ Generating: {localize_header(header) if output_language == 'ar' else header}")
        print(question)
        if output_language == "ar" and "English SMS Suggestions" in header:
            system_msg = english_sms_system_msg
        elif output_language == "ar":
            system_msg = arabic_sms_system_msg if "SMS" in header else arabic_plan_system_msg
        elif "Arabic" in header:
            system_msg=arabic_sms_system_msg
        elif "English" in header:
            system_msg=english_sms_system_msg
        else:
            system_msg=english_plan_system_msg
        # Call to OpenAI API for the answer
        answer = ask_openai(question, system_msg, company_name, company_url, campaign_brief, bitly_link, phone_number, cities, amman_direction, delivery_date, scraped_info)

        if output_language == "ar" and "Arabic SMS Suggestions" in header:
            answer = sanitize_arabic_sms_answer(answer)

        # Defensive cleanup: planning prompts occasionally return several report
        # sections in one answer. Keep only the section requested in this loop.
        result_header = localize_header(header) if output_language == "ar" else header
        if "SMS Suggestions" not in header:
            answer = _trim_answer_to_requested_section(answer, result_header, output_language)

        print(answer)

        # Store the analysis in the results
        result_header = localize_header(header) if output_language == "ar" else header
        results["analysis"][result_header] = {
            "header": result_header,
            "question": question,
            "answer": answer
        }

    # Save the results to a JSON file
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    return results
