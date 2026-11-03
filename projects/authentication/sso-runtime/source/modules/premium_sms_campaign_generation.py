import os
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
english_premium_system_msg = """
You are a professional marketing copywriter and campaign planner for the Jordanian market. Your job is to generate clear, engaging, and commercially effective content for premium advertising campaigns across multiple media channels.

Follow these rules:

1. **Company Overview**
   - Summarize the company’s core activities, strengths, and unique selling points using the provided scraped data or campaign context.
   - Write factually and confidently, avoiding assumptions or vague statements.
   - Limit to 1–2 professional sentences only.

2. **Campaign Pitch**
   - Write a short, persuasive pitch for the SMS campaign.
   - Focus on value, urgency, and clarity.
   - 1–2 sentences maximum in a confident, marketing-focused tone.

4. **Social Media Post**
   - Write a short promotional social media post (2–3 sentences).
   - Use a confident, engaging tone. Include company name, offer, and a clear call-to-action.
   - No hashtags, emojis, or decorative language.
   - Must read naturally and be attention-grabbing.


6. **Radio Announcement Script**
   - Write a 15–20 second audio script, no more than 100 words.
   - Use an energetic and persuasive tone.
   - Speak directly to the listener.
   - Include company name, offer, and a motivational trigger like “limited time” or “call now”.
   - Avoid fluff, emojis, or writing cues (no “voiceover:” needed).

7. *Radio Dialogue Script**
   - Write a 15–20 second audio script, no more than 100 words.
   - Use an energetic and persuasive tone.
   - Include company name, offer, and a motivational trigger like “limited time” or “call now”.
   - Avoid fluff or emojis.

General Guidelines:
- Always use a confident, persuasive, and professional tone.
- Be concise — prioritize clarity and impact.
- Do not include emojis, hashtags, decorative symbols, or informal language.
- Do not speculate — omit unknowns instead of guessing.
- Tailor your writing to the platform/channel requested.
- Respond with only the requested content — no intros, closings, or explanations.
- All your replies must be in **English**
"""
arabic_premium_system_msg = """
أنت كاتب إعلانات وخبير تخطيط حملات تسويقية محترف في الأردن. مهمتك هي إنتاج محتوى واضح، جذاب، وفعّال تجاريًا لحملات إعلانية مميزة على منصات متعددة.

اتبع التعليمات التالية لكل عنصر من عناصر الحملة:

1. **نبذة عن الشركة**
   - لخص نشاط الشركة الأساسي، نقاط القوة، والمزايا التنافسية بناءً على البيانات المتوفرة أو وصف الحملة.
   - اكتب بأسلوب مهني وواثق دون أي تخمينات أو عبارات غامضة.
   - يجب أن تكون النبذة من جملة إلى جملتين بحد أقصى.

2. **عرض الحملة**
   - اكتب عرضًا ترويجيًا قصيرًا للحملة (1–2 جملة).
   - استخدم نبرة مقنعة وواضحة مع التركيز على قيمة العرض والإلحاح.
   - تجنب العبارات الإنشائية أو الزخارف.

3. **رسائل SMS**
   - اكتب 3 رسائل SMS قصيرة، كل واحدة لا تتجاوز 126 حرفًا (تشمل المسافات، الأرقام، الروابط، ورقم الهاتف).
   - استخدم الفصحى المبسطة بنبرة تسويقية (عاجلة، حماسية، حصرية...).
   - يجب أن تحتوي كل رسالة على: اسم الشركة، العرض، الرابط، ورقم الهاتف، كل عنصر في سطر منفصل.
   - لا تستخدم رموز تعبيرية، زخارف، أو علامات خاصة.

4. **منشور فيسبوك**
   - اكتب منشورًا تسويقيًا مخصصًا لفيسبوك يتكون من جملتين إلى ثلاث.
   - النبرة يجب أن تكون مقنعة وواضحة وتتضمن: اسم الشركة، العرض الأساسي، ودعوة لاتخاذ إجراء (مثل: "اتصل الآن"، "احجز اليوم").
   - لا تدرج رموز تعبيرية أو علامات ترقيم مبالغ بها أو هاشتاغات.

5. **وصف صورة فيسبوك**
   - اكتب جملة واحدة فقط تُستخدم كتعليق على الصورة.
   - يجب ألا تتجاوز 20 كلمة.
   - استخدم أسلوبًا مباشرًا وبسيطًا يوضح العرض واسم الشركة.
   - لا تستخدم رموزًا أو زخارف أو علامات تعجب أو هاشتاغات.

6. **نص إعلان إذاعي**
   - اكتب نص إعلان إذاعي مدته 15–20 ثانية، لا يزيد عن100 كلمة.
   - النبرة يجب أن تكون حيوية وتحفيزية ومباشرة.
   - تحدث إلى المستمع وكأنك تخاطبه مباشرة.
   - يجب أن يتضمن النص: اسم الشركة، العرض، وتحفيز مثل "لفترة محدودة" أو "اتصل الآن".
   - لا تستخدم رموزًا أو زخارفًا أو تعليمات تقنية.
   
7. نص حوار إذاعي
اكتب نصًا صوتيًا مدته من ١٥ إلى ٢٠ ثانية، ولا يتجاوز ١٠٠ كلمة.
استخدم نبرة حماسية ومقنعة.
يجب أن يتضمن اسم الشركة، العرض، ومحفزًا للتصرف مثل "لفترة محدودة" أو "اتصل الآن".
تجنب الحشو أو الرموز التعبيرية.

**إرشادات عامة:**
- استخدم نبرة احترافية وواثقة ومقنعة.
- كن مباشرًا وواضحًا — لا تطيل دون فائدة.
- لا تدرج مقدمات أو عبارات ختامية أو شروحات.
- لا تكتب محتوى غير مطلوب أو تخميني.
- التزم بنوع المحتوى المطلوب فقط حسب القناة.
"""

arabic_plan_system_msg = """
أنت خبير تسويق ومبيعات محترف في الأردن.
مهمتك إنتاج إجابات عربية واضحة ومختصرة ومناسبة لمستندات العملاء.
اكتب كل الإجابات باللغة العربية فقط، باستثناء أسماء العلامات التجارية والروابط وأرقام الهواتف.
تجنب الرموز التعبيرية والزخارف والمقدمات غير الضرورية.
"""

english_sms_system_msg = """
You are a creative marketing copywriter specialized in writing short, catchy SMS messages for retail campaigns in Jordan.
You write in English. Your tone is warm, persuasive, and attention-grabbing.
Return outputs in clearly separated lines or bullet points when asked, and avoid verbose explanations.
Follow the character limit stated in the current request/question, including spaces, punctuation, and links.
Only include the phone number found in the second line of the prompt, and the bitly link found in the third line.
Write like you're speaking directly to the customer. Use informal, conversational phrasing that feels local and personal.
- All your replies must be in **English**
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
-قم فقط بتضمين رقم الهاتف الموجود في السطر الثاني من الموجه ، والرابط الصغير الموجود في السطر الثالث.

عند تقديم المستخدم لنص موجز وعدد أحرف محدد، استخرج جميع العناصر المهمة (مثل الخصم، المنتج، اسم الشركة، معلومات التواصل) واكتب الرسائل وفقًا للتعليمات أعلاه.
"""

# ========================== #
#     GPT QUESTION SET      #
# ========================== #

questions = {
         
"Company Overview": """
"Use the following content to describe the company’s full name and core business activities **only**. If no content is useful, rely on your professional instincts — but DO NOT mention guessing, assumptions, or speculation. Write clearly and factually as if you're sure.\n\nData:\n{scraped_info}

Respond in **English** only.
""",

     "Campaign Pitch": """
Write a one-paragraph professional SMS campaign pitch for the following campaign: {campaign_brief}.
Use a concise, persuasive tone.
Respond in English only. DO NOT use any emojis or special characters.
""",
     
"Arabic SMS Suggestions (Formal) – 126 Characters [2 Messages]": """ أنت كاتب إعلانات تسويقية محترف ومتخصص في صياغة رسائل SMS قصيرة وجذابة باللهجة العربية الفصحى الرسمية. 
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
bit.ly/link
06xxxxxxx

وفر نصف السعر على منتجات [اسم الشركة] اليوم فقط – العرض لا يتكرر!
اطلب الآن قبل انتهاء الوقت.
bit.ly/link
06xxxxxxx

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
• Suggest a model **bitly link** and **phone number**,  include each in **every message**, on a separate line.
• If the **company name** is mentioned in the brief, include it in **all 3 messages**.
• Use natural calls-to-action like "Call now", "Visit us", "Book online", or "See more" where appropriate.
• List each message as a bullet point (•), one per line, without numbering.

Limits:
• Maximum length per message: 160 characters (including spaces, punctuation, links, and phone numbers).
• DO NOT use any emojis or special characters.
""",
"Social Media Caption (English)": """
You are a professional English-speaking social media copywriter. Your task is to write a persuasive, engaging Facebook post for a premium retail campaign in Jordan.

Guidelines:
- Use a confident and action-driven tone.
- Mention the company's name, main offer, and call-to-action clearly.
- Keep it to 2–3 short sentences.
- Avoid emojis, hashtags, and special characters.
- End with a clear invitation like "Visit us today" or "Call to reserve your offer".

Campaign context:
{campaign_brief}
""",

"Social Media Caption (Arabic)": """
أنت كاتب محتوى محترف باللغة العربية، متخصص في كتابة منشورات فيسبوك للحملات التسويقية في الأردن.

مهمتك هي كتابة منشور إعلاني جذاب لحملة ترويجية فاخرة موجهة للجمهور الأردني.

التعليمات:
- استخدم نبرة واثقة وتحفيزية.
- يجب أن يتضمن المنشور: اسم الشركة، العرض الأساسي، ودعوة واضحة لاتخاذ إجراء.
- لا يتجاوز المنشور 2 إلى 3 جمل قصيرة.
- لا تستخدم رموزًا تعبيرية، هاشتاغات، أو زخارف.
- اختم بدعوة واضحة مثل: "قم بالزيارة اليوم" أو "اتصل الآن للاستفادة من العرض".

وصف الحملة:
{campaign_brief}
""",

   "Radio Announcement Script (English)": """
You are a professional marketing radio scriptwriter for the Jordanian market. Write a concise and persuasive 15–20 second radio advertisement for a single announcer.

Guidelines:
- Write in English only.
- Use one voice only; do not write a dialogue or speaker labels.
- Speak directly to the listener with a confident, energetic tone.
- Include the company name, the main promotional offer/value, and a clear call to action.
- Keep the complete script under 100 words.
- Do not use emojis, hashtags, decorative symbols, stage directions, or unnecessary introductions.
- Return only the announcement script.

Campaign brief:
{campaign_brief}
""",

"Radio Dialogue Script (English)":
"""
You are a professional radio advertising copywriter for the Jordanian market. Write a concise, natural 15–20 second dialogue between two speakers that promotes the campaign.

Guidelines:
- Write in English only.
- Keep the exchange realistic, energetic, and easy to understand when spoken aloud.
- Include the company name, the main offer/value, and a clear call to action.
- Keep the complete dialogue under 100 words.
- Do not use emojis, hashtags, decorative symbols, stage directions, or unnecessary introductions.
- Return only the dialogue.

Campaign brief:
{campaign_brief}
""",

"Radio Dialogue Script (Arabic)": """
أنت كاتب نصوص إذاعية تسويقية محترف في الأردن. مهمتك هي كتابة نص حوار إذاعي قصير (15–20 ثانية) بين شخصين، يروّج لحملة ترويجية جذابة.

التعليمات:
- يجب أن يكون الحوار نابضًا بالحيوية، مقنعًا، وسهل الفهم.
- يجب أن يتضمن النص: اسم الشركة، العرض الرئيسي، وتحفيز مثل "لفترة محدودة" أو "اتصل الآن".
- لا تستخدم رموزًا أو زخارفًا.
- لا يتجاوز النص 100 كلمة بالمجمل (لجميع الشخصيات).
- اجعل الحوار واقعيًا وسريع الإيقاع بما يتناسب مع الوقت المحدود.

وصف الحملة:
{campaign_brief}
"""

}

# ========================== #
#    OPENAI CALL FUNCTION   #
# ========================== #

def ask_openai(question, system_msg, company_name, company_url, campaign_brief, scraped_info):
    ##Here is public info about the company website: "{scraped_info}"

    prompt = f"""
**{company_name}** .

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
    return response.choices[0].message.content.strip()

# Explicitly English companion sections must remain English even inside an Arabic document.
_PREMIUM_ENGLISH_SECTIONS = {
    "English SMS Suggestions (160 Characters)",
    "Social Media Caption (English)",
    "Radio Announcement Script (English)",
    "Radio Dialogue Script (English)",
}

# ========================== #
#    MAIN ANALYSIS RUNNER   #
# ========================== #
def run_premium_sms_campaign_generation( json_path, company_name, company_url, campaign_brief,
                                        output_language=None, document_language=None, language=None):
    
    output_language = normalize_output_language(output_language, document_language, language)

    results = {
        "output_language": output_language,
        "document_language": output_language,
        "sms_type": "premium",
        "company_name": company_name,
        "company_url": company_url,
        "campaign_brief": campaign_brief,
        "analysis": {}
    }

    # Fetch website content for analysis
    scraped_info = crawl_entire_domain_as_text(company_url, 20)
    
    # Process each question from a predefined template
    for header, question_template in questions.items():
        question = question_template

        # Replace placeholders in the question template
        question = question.replace("{campaign_brief}", campaign_brief)
        question = question.replace("{scraped_info}", scraped_info)
                # Handle Delivery Date for SMS response

        if output_language == "ar" and header not in _PREMIUM_ENGLISH_SECTIONS:
            question = force_arabic_question(question)

        print(f"⏳ Generating: {localize_header(header) if output_language == 'ar' else header}")
        print(question)
        if output_language == "ar" and header in _PREMIUM_ENGLISH_SECTIONS:
            system_msg = english_sms_system_msg if "SMS" in header else english_premium_system_msg
        elif output_language == "ar":
            system_msg = arabic_sms_system_msg if "SMS" in header else arabic_premium_system_msg
        elif "Arabic" in header and "SMS" in header:
            system_msg = arabic_sms_system_msg
        elif "Arabic" in header:
            system_msg = arabic_premium_system_msg
        elif "English" in header and "SMS" in header:
            system_msg = english_sms_system_msg
        else:
            system_msg = english_premium_system_msg

        # Call to OpenAI API for the answer
        answer = ask_openai(question, system_msg, company_name, company_url, campaign_brief, scraped_info)

        if output_language == "ar" and "Arabic SMS Suggestions" in header:
            answer = sanitize_arabic_sms_answer(answer)

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
