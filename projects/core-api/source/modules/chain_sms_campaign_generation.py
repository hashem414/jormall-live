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
   - Exclude Fridays and public holidays unless explicitly stated otherwise.  
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


english_sms_system_msg = """
You are a creative marketing copywriter specialized in writing short, catchy SMS messages for retail campaigns in Jordan.
You write in English  with local Jordanian expressions where appropriate. Your tone is warm, persuasive, and attention-grabbing.
Return outputs in clearly separated lines or bullet points when asked, and avoid verbose explanations.
Your messages must be under  characters including spaces, punctuation, and links, unless otherwise stated.
Only include the phone number found in the second line of the prompt, and the bitly link found in the third line.
Write like you're speaking directly to the customer. Use informal, conversational phrasing that feels local and personal.
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
3. اكتب 2 رسائل باللهجة العامية الأردنية.
4. غيّر الأسلوب بين الرسائل (عاجلة، ودّية، حماسية، حصرية، مباشرة(.
5. إذا وُجد رابط أو رقم هاتف، اكتبه في **كل رسالة** في سطر منفصل.
6.لا تستخدم رموز تعبيرية (no emojis) أو زخارف أو رموز خاصة.
7.أخرج الرسائل على شكل 2أسطر، كل سطر رسالة واحدة فقط.

### ملاحظات ثقافية لجذب الجمهور الأردني:  مع أمثلة
- استخدم لغة قريبة من الناس مثل: (لحقها، لا تفوّت، حالًا، نص بالنص).
- ركّز على الإلحاح والندرة: (اليوم فقط، الكمية محدودة، العرض بينتهي).
- أبرز القيمة الكبيرة: (وفر نص السعر، خصم 50%، أرخص سعر بالسوق).
- اجعل الدعوة للتحرك واضحة: (اطلب هلأ، اتصل الآن، احجز اليوم).


### أمثلة عامية أردنية:
الكمية محدودة! نص السعر هسا من [اسم الشركة]… الحقها!
bit.ly/link
06xxxxxxx

لا تتأخر… أقوى العروض من [اسم الشركة] مستنياك!
bit.ly/link
06xxxxxxx
### وصف الحملة:
{campaign_brief}

الآن، أكتب 2 رسائل SMS قوية ومؤثرة حماسية بالعامية بناءً على الوصف أعلاه.

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
bit.ly/link
06xxxxxxx

وفر نصف السعر على منتجات [اسم الشركة] – العرض محدود
bit.ly/link
06xxxxxxx

### وصف الحملة:
{campaign_brief}

الآن، أكتب 2 رسائل SMS قوية ومؤثرة حماسية بالفصحى الرسمية بناءً على الوصف أعلاه.
""",

"Arabic SMS Suggestions (Formal - 126 Characters)": """ أنت كاتب إعلانات تسويقية محترف ومتخصص في صياغة رسائل SMS قصيرة وجذابة باللهجة العربية الفصحى الرسمية. 
مهمتك هي ابتكار رسائل إعلانية قوية تقنع العميل باتخاذ إجراء فوري.

### الشروط:
1. طول كل رسالة لا تتجاوز ال "126" حرفًا، بما في ذلك المسافات، الأرقام، الروابط، وعلامات الترقيم.
2. كل رسالة يجب أن تحتوي على تفاصيل الحملة (الخصومات، الأسعار، الرابط، ورقم الهاتف، واسم الشركة).
3. اكتب 2 رسائل باللهجة الفصحى الرسمية.
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
الآن، أكتب 2 رسائل SMS قوية ومؤثرة حماسية بالفصحى الرسمية بناءً على الوصف أعلاه.
""",

    "English SMS Suggestions (160 Characters)": """
Suggest 3 SMS marketing messages in **English** for the following offer: {campaign_brief}.
Use a friendly, engaging tone.

Rules:
• If a **bitly link** or **phone number** is present, include it in **every message**, each on a separate line.
• If both are present, include both (each on its own line) in **every message**.
• If a **phone number** or **URL** appears in the brief, include one or both in **all 2 messages**.
• If the **company name** is mentioned in the brief, include it in **all 2 messages**.
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
Exclude Fridays and public holidays.
Respond in **English** only. DO NOT use any emojis.
{cities}
{amman_direction}
""",
   
"Company Overview": """
"Use the following content to describe the company’s full name and core business activities. If no content is useful, rely on your professional instincts — but DO NOT mention guessing, assumptions, or speculation. Write clearly and factually as if you're sure.
Respond in **English** only.
"""
}

# ========================== #
#    OPENAI CALL FUNCTION   #
# ========================== #

def ask_openai(question, system_msg, company_name, company_url, campaign_brief, chain_message, chain_date, delivery_times, cities, amman_direction, scraped_info):
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
    print(response)
    return response.choices[0].message.content.strip()

# ========================== #
#    MAIN ANALYSIS RUNNER   #
# ========================== #
def run_chain_sms_campaign_generation(
    json_path, company_name, company_url, chain_campaign_title, campaign_brief,
    chain_messages, chain_delivery_dates,chain_delivery_times,
    cities=None, amman_direction=None
):
    results = {
        "sms_type": "chain",
        "company_name": company_name,
        "company_url": company_url,
        "chain_campaign_title":chain_campaign_title,
        "campaign_brief": campaign_brief,
        "chain_messages": chain_messages,
        "chain_delivery_dates": chain_delivery_dates,
        "chain_delivery_times":chain_delivery_times,
        "cities": cities,
        "amman_direction": amman_direction,
        "analysis": {}
    }

    # Load scraped content from website
    scraped_info = crawl_entire_domain_as_text(company_url, 20)

    # Set today's date as fallback
    today_date = datetime.datetime.now().strftime("%d-%m-%Y")

    # === 1. Run questions that execute only once ===
    for header in ["Company Overview", "Target Audience"]:
        question = questions[header]
        question = question.replace("{scraped_info}", str(scraped_info))

        if cities and amman_direction:
            question = question.replace("{cities}", f"Geographical location: {cities}, {amman_direction} Amman")
        elif cities:
            question = question.replace("{cities}", f"Geographical location: {cities}")
        elif amman_direction:
            question = question.replace("{amman_direction}", f"Geographical location: {amman_direction} Amman")

        system_msg = english_plan_system_msg
        answer = ask_openai(question, system_msg, company_name, company_url, campaign_brief, chain_messages, chain_delivery_dates, chain_delivery_times, cities, amman_direction, scraped_info)
        
        results["analysis"][header] = {
            "header": header,
            "question": question,
            "answer": answer
        }

    # === 2. Run per-message questions in specific order ===
    per_message_questions = [
        "Campaign Pitch",
        "Arabic SMS Suggestions (Casual - 70 Characters)",
        "Arabic SMS Suggestions (Formal - 70 Characters)",
        "Arabic SMS Suggestions (Formal - 126 Characters)",
        "English SMS Suggestions (160 Characters)"
    ]

    for i in range(len(chain_messages)):
        pitch = chain_messages[i]
        delivery_date = chain_delivery_dates[i] if i < len(chain_delivery_dates) else today_date
        delivery_time = chain_delivery_times[i] if i<len(chain_delivery_times) else today_date
        for header in per_message_questions:
            question = questions[header]
            question = question.replace("{campaign_brief}", str(pitch))
            question = question.replace("{delivery_date}", str(delivery_date))
            question = question.replace("{scraped_info}", str(scraped_info))

            if cities and amman_direction:
                question = question.replace("{cities}", f"Geographical location: {cities}, {amman_direction} Amman")
            elif cities:
                question = question.replace("{cities}", f"Geographical location: {cities}")
            elif amman_direction:
                question = question.replace("{amman_direction}", f"Geographical location: {amman_direction} Amman")

            # Choose the appropriate system message
            if "Arabic" in header:
                system_msg = arabic_sms_system_msg
            elif "English" in header:
                system_msg = english_sms_system_msg
            else:
                system_msg = english_plan_system_msg

            print(f"⏳ Generating: {header} for Message {i + 1}")
            answer = ask_openai(
                question,
                system_msg,
                company_name,
                company_url,
                pitch,             # campaign_brief used here as pitch
                pitch,             # single message (not list)
                delivery_date,     # single delivery date (not list)
                delivery_time,
                cities,
                amman_direction,
                scraped_info
            )

       
            results["analysis"][f"{header} - Message {i + 1}"] = {
                "header": header,
                "message_index": i + 1,
                "pitch": pitch,
                "delivery_date": delivery_date,
                "delivery_time":delivery_time,
                "question": question,
                "answer": answer
            }

    # Save to file
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    return results
