import os
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv
import datetime
# ========================== #
#      INITIAL SETUP        #
# ========================== #

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ========================== #
#     WEBSITE SCRAPER       #
# ========================== #
from .website_crawler_scrapper import crawl_entire_domain_as_text

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



english_sms_system_msg = """
You are a creative marketing copywriter specialized in writing short, catchy SMS messages for retail campaigns in Jordan.
You write in English. Your tone is warm, persuasive, and attention-grabbing.
Return outputs in clearly separated lines or bullet points when asked, and avoid verbose explanations.
Your messages must be under  characters including spaces, punctuation, and links, unless otherwise stated.
Only include the phone number found in the second line of the prompt, and the bitly link found in the third line.
Write like you're speaking directly to the customer. Use informal, conversational phrasing that feels local and personal.
- All your replies must be in **English**
"""
arabic_sms_system_msg = """
أنت كاتب إعلانات إبداعي متخصص في كتابة رسائل SMS ترويجية قصيرة وجذابة للحملات التسويقية في الأردن.

تكتب باللغة العربية الفصحى الحديثة، مع استخدام تعبيرات محلية مألوفة في الأردن عند الحاجة. نبرة كتابتك دافئة، مقنعة، وتلفت الانتباه.

يجب أن تتوفر في كل رسالة الشروط التالية:
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
You are a professional marketing radio scriptwriter based in Jordan.
Your task is to write a short, 15–20 second radio dialogue between two people that promotes an attractive campaign.
Instructions:
The dialogue should be lively, persuasive, and easy to understand.
The script must include: the company name, the main promotional offer, and a motivator like “limited time only” or “call now.”
Do not use emojis or decorative elements.
The total word count (for both characters) must not exceed 100 words.
Keep the conversation realistic and fast-paced to fit the time limit.
Campaign Description:
{campaign_brief}
""",

"Radio Dialogue Script (English)":
"""
أنت كاتب نصوص إعلانات إذاعية محترف متخصص في السوق الأردني. مهمتك هي كتابة نص إعلان إذاعي مقنع ومختصر (مدة 15–20 ثانية) بصوت واحد فقط.

**الإرشادات:**

* خاطب المستمع مباشرة بنبرة واثقة وحيوية.
* تضمَّن اسم الشركة، العرض الترويجي الرئيسي، وتحفيزًا لاتخاذ إجراء (مثل: "لفترة محدودة"، "اتصل الآن"، "لا تفوت الفرصة").
* تجنّب استخدام الرموز التعبيرية أو الزخارف أو اللغة التجميلية.
* يجب ألا يتجاوز النص 100 كلمة.

**موجز الحملة:**
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

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        top_p=0.95,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
    )
    return response.choices[0].message.content.strip()

# ========================== #
#    MAIN ANALYSIS RUNNER   #
# ========================== #
def run_premium_sms_campaign_generation( json_path, company_name, company_url, campaign_brief):
    
    results = {
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

        print(f"⏳ Generating: {header}")
        print(question)
        if "Arabic" in header and "SMS" in header:
            system_msg = arabic_sms_system_msg
        elif "Arabic" in header:
            system_msg = arabic_premium_system_msg
        elif "English" in header and "SMS" in header:
            system_msg = english_sms_system_msg
        else:
            system_msg = english_premium_system_msg

        # Call to OpenAI API for the answer
        answer = ask_openai(question, system_msg, company_name, company_url, campaign_brief, scraped_info)

        print(answer)

        # Store the analysis in the results
        results["analysis"][header] = {
            "header": header,
            "question": question,
            "answer": answer
        }

    # Save the results to a JSON file
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    return results
