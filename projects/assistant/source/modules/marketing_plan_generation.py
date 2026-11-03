import os
import json
from dotenv import load_dotenv
from .openai_client import create_openai_client

load_dotenv()

def get_openai_client():
    """Create the OpenAI client only when an AI generation action is used."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('\"').strip("'")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file beside app.py, then restart the app.")
    return create_openai_client(api_key)
from .website_crawler_scrapper import crawl_entire_domain_as_text


questions = {
    "Company Overview": "What is the company's full name, core business activities?",
    "SMS Potential and Benefits": (
        "How can the company benefit from using SMS advertising — in terms of customer reach, engagement, conversions, or service reminders? "
        "Provide examples per each benefit suggested and one sample SMS message (160 characters max)."
    ),
"SWOT Analysis": """What are the company's key Strengths, Weaknesses, Opportunities, and Threats (SWOT) in its market?""",
"SMS Content Strategy": ("""
Role:
You are a professional SMS marketing strategist. Your task is to generate structured SMS Content Strategies.
Instructions:
Always provide at least three SMS content samples. For each sample, include the following fields exactly in this order:
Date & Time: [Specify exact day, date, and time of sending in 2026]
Objective: [State the campaign’s main goal]
Content in English: [Engaging, short, and professional SMS text]
Content in Arabic: [Accurate Arabic marketing translation, natural and appealing]
Target Audience: [Define by location, gender, age range, interests/behavior]
Requirements:
Keep each SMS under 160 characters when possible.
Ensure English and Arabic content feel equally compelling.
Use realistic marketing objectives (e.g., launch announcement, flash sale, VIP invitation) when suitable.
Vary the tone to match different audience segments (trendy, urgent, elegant).
At the end of the strategy, add a concluding summary paragraph explaining how the messages are timely, relevant, and engaging.
Output Format:
**1. SMS Content Sample:**

- Date & Time: …
- Objective: …
- Content in English: …
- Content in Arabic: …
- Target Audience: …

**2. SMS Content Sample:**

- Date & Time: …
- Objective: …
- Content in English: …
- Content in Arabic: …
- Target Audience: …

**3. SMS Content Sample:**

- Date & Time: …
- Objective: …
- Content in English: …
- Content in Arabic: …
- Target Audience: …

Summary

"""),
    "Target Audience Segmentation": (
        """Role:
        You are a marketing strategist. Your task is to generate a Target Audience Segmentation tailored to a specific brand, product, or location in Jordan for the client.
Instructions:
Provide at least five clear audience segments.
Each segment should include a descriptive title (e.g., “Young Professionals and Families”) and a short explanation of their characteristics, motivations, and buying behaviors.
Segments should reflect income, lifestyle, demographics, geography, and psychographics when relevant.
Ensure descriptions are concise and actionable.
End with a short summary paragraph explaining how these segments can guide tailored marketing strategies.
Output Format:
For [Brand/Store Name] in [Location], focusing on the [Market/Industry], the target audience is likely segmented as follows:

1. [Segment Title]: [Short description of characteristics and behavior]

2. [Segment Title]: [Short description of characteristics and behavior]

3. [Segment Title]: [Short description of characteristics and behavior]

4. [Segment Title]: [Short description of characteristics and behavior]

5. [Segment Title]: [Short description of characteristics and behavior]

Understanding these segments can help tailor marketing strategies to effectively reach and engage them."""
    ),

    "SMS Timing Strategy (Scheduling)":("""Role:
You are an SMS marketing strategist specializing in consumer behavior in the Middle East. Your task is to generate an SMS Timing Strategy (Scheduling) for the client.
Instructions:
Provide 3–4 recommended time slots for sending SMS messages, each with a time range and a short rationale explaining why it is effective.
Include day-of-week guidance (e.g., weekdays vs. weekends, specific best-performing days).
Follow Jordan Telecommunications Regulatory Commission (TRC) rules for promotional bulk SMS: do not schedule promotional messages on Friday, Saturday, official or religious holidays, or national occasions; on weekdays, do not schedule them during the restricted period from 9:00 PM until 7:00 AM unless TRC approval applies.
Contextualize the timing to local consumer behavior in the brand’s market (e.g., shopping habits, work schedules, cultural routines).
End with a short summary paragraph on how continuous data analysis can further refine SMS timing for maximum engagement.
Output Format:
**SMS Timing Strategy (Scheduling)**

For [Company] in [Location], SMS timing should be optimized for maximum engagement and effectiveness. Based on [Market/Consumer Behavior], consider sending promotional SMS messages during the following times:

1. [Time Range]: [Rationale for effectiveness]

2. [Time Range]: [Rationale for effectiveness]

3. [Time Range]: [Rationale for effectiveness]

(Optionally include a 4th if useful)

[Day-of-week recommendations]

[Summary paragraph about continuous optimization through local engagement metrics]  """),

"Client Promotion Integration":("""Role:
You are a retail marketing strategist. Your task is to generate in-store activity ideas that increase customer footfall and/or conversion of the client.
Instructions:
Provide at least 6–8 actionable in-store activities.
Each idea should include:
Activity Title (short and engaging)
Description (how the activity works in-store)
Objective (what it achieves: more visits, higher sales, stronger engagement, etc.)
Ideas must be creative, practical, and relevant to the specified industry.
Balance between short-term sales boosters (promotions, demos) and long-term loyalty drivers (events, memberships, community engagement).
End with a summary paragraph explaining how these activities can combine to build stronger customer traffic and revenue.
Output Format:

1. [Activity Title]  
   - Description: …  
   - Objective: …  

2. [Activity Title]  
   - Description: …  
   - Objective: …  

3. [Activity Title]  
   - Description: …  
   - Objective: …  

[Continue up to 6–8 ideas]  

Summary: [Explain how these activities together will increase traffic and sales, tailored to the industry.]  """)
}


ARABIC_HEADERS = {
    "Company Overview": "نظرة عامة على الشركة",
    "SMS Potential and Benefits": "إمكانات وفوائد الرسائل القصيرة",
    "SWOT Analysis": "تحليل نقاط القوة والضعف والفرص والتهديدات",
    "SMS Content Strategy": "استراتيجية محتوى الرسائل القصيرة",
    "Target Audience Segmentation": "تقسيم الجمهور المستهدف",
    "SMS Timing Strategy (Scheduling)": "استراتيجية توقيت وجدولة الرسائل القصيرة",
    "Client Promotion Integration": "تكامل الأنشطة الترويجية للعميل",
}

def _is_arabic_report_language(value):
    return str(value or "").strip().lower() in {"ar", "arabic", "العربية", "عربي"}

system_msg = """
You are a professional business analyst. Focus only on answering the specific question given. Use the provided website content or manual company description as primary context. Be concise, objective, and relevant to Jordanian market behavior.
"""
# ======================
# OPENAI HELPER
# ======================
def ask_openai(question_text, company, url_or_text, language, context_text):
    is_arabic = str(language or "").strip().lower() in {"arabic", "ar", "العربية", "عربي"}
    arabic_structure_rule = """
    Arabic document requirements (mandatory):
    - Answer ONLY the current requested section. Do not repeat or generate other report sections.
    - Translate ALL structural headings and field labels into Arabic.
    - Never leave labels such as: SMS Content Sample, Date & Time, Time & Date, Objective, Content in English, Content in Arabic, Target Audience, Audience Target, Description, Recommendations, or Summary in English.
    - Use these Arabic labels when relevant: نموذج محتوى رسالة قصيرة، التاريخ والوقت، الهدف، المحتوى بالإنجليزية، المحتوى بالعربية، الجمهور المستهدف، الوصف، التوصيات، الملخص.
    - English is allowed only inside the actual English SMS message text, brand names that have no Arabic form, URLs, emails, and phone numbers.
    - Keep Arabic prose concise, polished, and naturally RTL.
    """ if is_arabic else ""

    prompt = f"""
    Company: {company}
    Source: {url_or_text}

    Context:
    {context_text[:10000]}

    Question: {question_text}

    Answer in {language}.

    Formatting requirements:
    - Use clean Markdown structure, not raw HTML.
    - Use short paragraphs and descriptive headings only when useful.
    - Use hyphen bullets for lists and numbered lists for ordered steps or samples.
    - Use **bold labels** for fields such as Objective, Target Audience, Date & Time, Strengths, and Recommendations.
    - Do not wrap the answer in a code block.
    - If the requested language is Arabic, write polished Modern Standard Arabic and keep the complete answer naturally right-to-left.
    {arabic_structure_rule}
    """
    try:
        response = get_openai_client().chat.completions.create(
            model="gpt-5.5",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ OpenAI API failed: {e}")
        return "[Not available]"

# ======================
# MAIN FUNCTION
# ======================
def run_marketing_plan_generation(company_name, report_language, json_path, company_url=None, company_about=None):
    """
    Generates a marketing plan report for a company.
    Can use either a URL (scraping) or a manual text description.
    """

    # Determine source type
    if company_about and company_about.strip():
        print("📘 Using manual company description for marketing plan")
        source_label = "Manual Description"
        scraped_text = company_about.strip()
    elif company_url and company_url.strip():
        print("🌐 Scraping website for marketing plan...")
        try:
            scraped_text = crawl_entire_domain_as_text(company_url.strip(), 20)
            source_label = company_url
        except Exception as e:
            print(f"⚠️ Scraping failed for {company_url}: {e}")
            scraped_text = "[No content available due to failed scraping]"
            source_label = company_url
    else:
        print("⚠️ No input source provided.")
        scraped_text = "[No data provided]"
        source_label = "N/A"

    # Initialize result dictionary
    is_arabic = _is_arabic_report_language(report_language)
    results = {
        "marketing_plan": True,
        "company_name": company_name,
        "company_source": source_label,
        "report_language": "Arabic" if is_arabic else "English",
        "output_language": "ar" if is_arabic else "en",
        "document_language": "ar" if is_arabic else "en",
        "analysis": {}
    }

    # Process each question
    for key, question in questions.items():
        header = ARABIC_HEADERS.get(key, key) if is_arabic else key
        print(f"⏳ Generating: {header}")
        answer = ask_openai(question, company_name, source_label, "Arabic" if is_arabic else "English", scraped_text)

        if answer and answer != '[Not available]':
            print(answer)
            results["analysis"][key] = {
                "header": header,
                "original_header": key,
                "question": question,
                "answer": answer
            }
        else:
            print(f"⚠️ Skipping {key}: no valid response")

    # Save results to JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print(f"✅ Marketing plan generated for {company_name}")
    return results

#
# if __name__ == "__main__":
#     # Example usage
#     company_name = "Daraghmeh Jordan"
#     company_url = "https://www.Daraghmeh.com/"
#     report_language = "English"
#     json_path = "Daraghmeh_company_analysis.json"
#
#     analysis_results = run_profile_analysis_generation(company_name, company_url, report_language, json_path)
#     print("Analysis complete. Results saved to:", json_path)
