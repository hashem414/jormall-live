import requests
from bs4 import BeautifulSoup
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from .website_crawler_scrapper import crawl_entire_domain_as_text

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =======================
# QUESTIONS CONFIGURATION
# =======================
questions = {
    "Company Overview": "What is the company's full name and its main business activities?",
    "SMS Potential and Benefits": (
        "How can the company benefit from using SMS advertising — in terms of customer reach, engagement, conversions, or service reminders? "
        "Provide examples per each benefit and include one sample SMS message (160 characters max)."
    ),
    "Strategic Advantage": (
        "What market challenges or goals (e.g., awareness, sales, loyalty) can JorMall's SMS service help the company solve or improve?"
    )
}

# =======================
# SYSTEM MESSAGE
# =======================
system_msg = """
You are a professional business analyst. 
Focus only on answering the specific question given. 
Use the website content or provided description as your primary context.
Be concise, objective, and relevant to Jordanian market behavior.
"""

# =======================
# ASK OPENAI HELPER
# =======================
def ask_openai(question_text, company, url_or_text, language, context_text):
    """Send structured prompt to OpenAI and return clean answer."""
    prompt = f"""
    Company: {company}
    Source: {url_or_text}

    Context Information:
    {context_text[:10000]}  # limit to first 10k chars to stay efficient

    Question: {question_text}

    Answer in {language}.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=1.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ OpenAI request failed: {e}")
        return "[Not available]"

# =======================
# MAIN FUNCTION
# =======================
def run_profile_analysis_generation(company_name, report_language, json_path, company_url=None, company_about=None):
    """
    Generate a company profile report.
    - If company_about is provided → use that text.
    - Else → attempt to scrape the company_url.
    """

    # Determine input source
    if company_about and company_about.strip():
        print("📘 Using manual company description (textbook mode)")
        source_label = "Manual Description"
        scraped_text = company_about.strip()
    elif company_url and company_url.strip():
        print("🌐 Scraping company website...")
        try:
            scraped_text = crawl_entire_domain_as_text(company_url.strip(), 20)
            source_label = company_url
        except Exception as e:
            print(f"⚠️ Scraping failed for {company_url}: {e}")
            scraped_text = "[No content available due to failed scraping]"
            source_label = company_url
    else:
        print("⚠️ No valid input source provided (neither URL nor text)")
        scraped_text = "[No data provided]"
        source_label = "N/A"

    # Prepare results dictionary
    results = {
        "company_profile": True,
        "company_name": company_name,
        "company_source": source_label,
        "report_language": report_language,
        "analysis": {}
    }

    # Generate answers for each question
    for key, question in questions.items():
        print(f"⏳ Generating: {key}")
        answer = ask_openai(question, company_name, source_label, report_language, scraped_text)

        if answer and answer != '[Not available]':
            print(answer)
            results["analysis"][key] = {
                "header": key,
                "question": question,
                "answer": answer
            }
        else:
            print(f"⚠️ Skipping {key} — no valid response")

    # Save to JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print(f"✅ Profile report generated for {company_name}")
    return results