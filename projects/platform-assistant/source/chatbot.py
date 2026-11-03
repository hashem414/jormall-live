import csv
import re
import time
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from model_config import OPENAI_CHAT_MODEL, log_openai_model, public_path
from vector_store import load_vector_store


RETRIEVER_K = 8
RETRIEVER_FETCH_K = 20
MAX_SOURCE_SNIPPET = 180
APP_ROOT = Path(__file__).resolve().parent


arabic_system_prompt = """
أنت مساعد ودود وذكي تابع لـ JorMall. أجب فقط باستخدام المعلومات الواردة في سياق الوثيقة أدناه.

عند الرد على الأسئلة التي تتطلب شرح خطوات أو واجهات استخدام، إذا كانت هناك أوصاف صور بصيغة [Image: ...]، فتأكد من تضمينها في الموضع المناسب داخل الإجابة.

عند تقديم بيانات منظمة مثل جداول الميزات أو حدود الرسائل أو المقارنات، استخدم تنسيق الجدول Markdown لعرض المعلومات بشكل واضح.

لا تغير أو تعيد صياغة أوصاف الصور أو أسماء الشاشات.

إذا لم تجد الإجابة، قل: لم أجد المعلومة المطلوبة في الوثيقة. لمزيد من التفاصيل يرجى التواصل معنا على الإيميل support@jormall.com

لا تضف أي معلومات من عندك.

{context}

السؤال: {question}
الإجابة المفصلة:
"""


english_system_prompt = """
You are a helpful assistant for JorMall. Use only the information in the context below.

When the source contains image descriptions in the format [Image: ...], include them exactly where they appear in the answer. Do not move or paraphrase them.

Preserve exact captions and screen labels.
When presenting structured data such as feature lists, message limits, or comparisons, use a Markdown table format to ensure clarity.

If the answer is not found, reply with: I couldn't find the requested information in the document. For more details, contact us at support@jormall.com.

Do not add any information from your own knowledge.

{context}

Question: {question}
Detailed answer:
"""


condense_prompt = PromptTemplate.from_template(
    "Given the conversation and a follow-up question, rewrite the follow-up as a standalone question. "
    "Preserve the user's language. Do not answer the question.\n\n"
    "Chat History:\n{chat_history}\n\n"
    "Follow-up Input: {question}\n"
    "Standalone question:"
)


_vectorstore = None
_retriever = None
_translation_llm = None
_final_llm = None


def is_arabic(text):
    return bool(re.search(r'[\u0600-\u06FF]', text))


def get_translation_llm():
    global _translation_llm
    if _translation_llm is None:
        _translation_llm = ChatOpenAI(model_name=OPENAI_CHAT_MODEL, temperature=0)
    return _translation_llm


def get_final_llm():
    global _final_llm
    if _final_llm is None:
        _final_llm = ChatOpenAI(model_name=OPENAI_CHAT_MODEL, temperature=0.3)
    return _final_llm


def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = load_vector_store()
    return _vectorstore


def get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = get_vectorstore().as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": RETRIEVER_K,
                "fetch_k": RETRIEVER_FETCH_K,
                "score_threshold": 0.4,
            },
        )
    return _retriever


def translate_to_english(text):
    try:
        log_openai_model("translation", OPENAI_CHAT_MODEL)
        response = get_translation_llm().invoke([
            {"role": "system", "content": "Translate the following Arabic query to English. Return only the translation."},
            {"role": "user", "content": text},
        ])
        return response.content.strip()
    except Exception as e:
        print(f"[PERF] translation_failed error={type(e).__name__}", flush=True)
        return text


def normalize_simple_text(text):
    lowered = text.strip().lower()
    lowered = re.sub(r'[\s\.\!\?؟،,;:]+', ' ', lowered)
    return lowered.strip()


def basic_conversational_response(query, is_ar):
    normalized = normalize_simple_text(query)
    if not normalized:
        return None

    english_greetings = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}
    english_thanks = {"thanks", "thank you", "thx"}
    english_help = {"help", "who are you", "what can you do"}

    arabic_greetings = {"مرحبا", "مرحباً", "اهلا", "أهلا", "أهلاً", "السلام عليكم", "هلا"}
    arabic_thanks = {"شكرا", "شكراً", "يعطيك العافية"}
    arabic_help = {"مساعدة", "ساعدني", "من انت", "من أنت", "ماذا تستطيع"}

    if normalized in english_greetings:
        return "Hello. I can help answer questions about the JorMall platform and SMS regulations using the available documents."
    if normalized in english_thanks:
        return "You're welcome. Ask me any question about the JorMall platform or SMS regulations."
    if normalized in english_help:
        return "I can answer document-based questions about JorMall platform usage, login steps, SMS sending rules, and related TRC regulations."

    if normalized in arabic_greetings:
        return "مرحباً. يمكنني مساعدتك في الأسئلة المتعلقة بمنصة JorMall وتعليمات الرسائل القصيرة حسب الوثائق المتاحة."
    if normalized in arabic_thanks:
        return "على الرحب والسعة. يمكنك سؤالي عن منصة JorMall أو تعليمات الرسائل القصيرة."
    if normalized in arabic_help:
        return "يمكنني الإجابة عن الأسئلة المبنية على الوثائق حول استخدام منصة JorMall، خطوات الدخول، قواعد إرسال الرسائل، وتعليمات هيئة تنظيم قطاع الاتصالات."

    return None


def format_chat_history(chat_history):
    if not chat_history:
        return ""
    lines = []
    for user_text, bot_text in chat_history:
        lines.append(f"User: {user_text}")
        lines.append(f"Assistant: {bot_text}")
    return "\n".join(lines)


def is_likely_followup(query, is_ar):
    normalized = normalize_simple_text(query)
    words = normalized.split()

    if is_ar:
        indicators = [
            "هذا", "هذه", "ذلك", "تلك", "هو", "هي", "منها", "منهم",
            "الأول", "الأولى", "الثاني", "الثانية", "أي واحد", "أي منها",
        ]
    else:
        indicators = [
            "it", "that", "this", "those", "these", "they", "them",
            "which one", "which platform", "what about", "how about",
            "the first", "the second", "same",
        ]

    return len(words) <= 7 or any(indicator in normalized for indicator in indicators)


def invoke_retriever(retriever, query):
    if hasattr(retriever, "invoke"):
        return retriever.invoke(query)
    return retriever.get_relevant_documents(query)


def log_sources(source_documents):
    for idx, doc in enumerate(source_documents, start=1):
        metadata = doc.metadata or {}
        snippet = re.sub(r'\s+', ' ', doc.page_content[:MAX_SOURCE_SNIPPET]).strip()
        snippet = snippet.encode("ascii", "backslashreplace").decode("ascii")
        print(
            "[SRC] "
            f"{idx} file={metadata.get('file', '')} "
            f"section={metadata.get('section', '')} "
            f"chars={len(doc.page_content)} "
            f"snippet={snippet}",
            flush=True,
        )


def load_image_map(csv_path=None):
    csv_path = Path(csv_path) if csv_path else APP_ROOT / "image_map.csv"
    image_dict = {}
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            alt = row['alt_text'].strip()
            img = row['image_file'].strip()
            ar = row.get('arabic_caption', '').strip()
            image_dict[alt] = {'file': img, 'caption': ar or alt}
    return image_dict


image_map = load_image_map()


def replace_alt_text_with_image(text):
    pattern = re.compile(r"\[Image:\s*(.*?)\]", re.IGNORECASE)

    def replace_match(match):
        alt_text = match.group(1).strip()
        item = image_map.get(alt_text)
        if item:
            image_url = public_path(f"/static/images/{item['file']}")
            return f"![{item['caption']}]({image_url})"
        return match.group(0)

    return pattern.sub(replace_match, text)


def append_relevant_images(result_text, answer, source_documents):
    source_text = "\n".join(doc.page_content for doc in source_documents)
    image_mentions = re.findall(r"\[Image:\s*(.*?)\]", source_text)

    for alt in image_mentions:
        if f"[Image: {alt}]" in answer and f"![{alt}]" not in result_text:
            item = image_map.get(alt)
            if item:
                image_url = public_path(f"/static/images/{item['file']}")
                img_md = f"![{item['caption']}]({image_url})"
                result_text += f"\n\n{img_md}"
    return result_text


def generate_response(query, chat_history=None):
    chat_history = chat_history or []
    total_start = time.perf_counter()
    model_calls = 0

    step_start = time.perf_counter()
    is_ar = is_arabic(query)
    language_detection_time = time.perf_counter() - step_start

    basic_response = basic_conversational_response(query, is_ar)
    if basic_response:
        print(
            "[PERF] "
            f"lang={'ar' if is_ar else 'en'} "
            f"fast_path=basic_conversation "
            f"language_detection={language_detection_time:.3f}s "
            "translation=0.000s vectorstore_load=0.000s retrieval=0.000s "
            "retrieved_chunks=0 context_chars=0 condensation=0.000s generation=0.000s "
            f"llm_calls=0 image_post=0.000s total={time.perf_counter() - total_start:.3f}s",
            flush=True,
        )
        return {"result": basic_response, "source_documents": [], "used_rag": False}

    final_question = query
    condensation_time = 0.0
    if chat_history and is_likely_followup(query, is_ar):
        step_start = time.perf_counter()
        history_text = format_chat_history(chat_history)
        log_openai_model("condensation", OPENAI_CHAT_MODEL)
        condensed = get_final_llm().invoke(
            condense_prompt.format(chat_history=history_text, question=query)
        )
        final_question = condensed.content.strip() or query
        condensation_time = time.perf_counter() - step_start
        model_calls += 1

    translation_time = 0.0
    retrieval_query = final_question
    if is_ar:
        step_start = time.perf_counter()
        retrieval_query = translate_to_english(final_question)
        translation_time = time.perf_counter() - step_start
        model_calls += 1

    step_start = time.perf_counter()
    retriever = get_retriever()
    vectorstore_load_time = time.perf_counter() - step_start

    step_start = time.perf_counter()
    source_documents = invoke_retriever(retriever, retrieval_query)
    retrieval_time = time.perf_counter() - step_start
    context_chars = sum(len(doc.page_content) for doc in source_documents)

    log_sources(source_documents)

    context = "\n\n".join(doc.page_content for doc in source_documents)
    qa_prompt = PromptTemplate.from_template(
        arabic_system_prompt if is_ar else english_system_prompt
    )

    step_start = time.perf_counter()
    log_openai_model("final_answer", OPENAI_CHAT_MODEL)
    answer_response = get_final_llm().invoke(
        qa_prompt.format(context=context, question=final_question)
    )
    generation_time = time.perf_counter() - step_start
    model_calls += 1

    answer = answer_response.content.strip()

    step_start = time.perf_counter()
    result_text = replace_alt_text_with_image(answer)
    result_text = append_relevant_images(result_text, answer, source_documents)
    image_post_time = time.perf_counter() - step_start

    print(
        "[PERF] "
        f"lang={'ar' if is_ar else 'en'} "
        f"models=translation:{OPENAI_CHAT_MODEL if is_ar else 'none'},final:{OPENAI_CHAT_MODEL} "
        f"language_detection={language_detection_time:.3f}s "
        f"translation={translation_time:.3f}s "
        f"vectorstore_load={vectorstore_load_time:.3f}s "
        f"retrieval={retrieval_time:.3f}s "
        f"retrieved_chunks={len(source_documents)} "
        f"context_chars={context_chars} "
        f"condensation={condensation_time:.3f}s "
        f"generation={generation_time:.3f}s "
        f"llm_calls={model_calls} "
        f"image_post={image_post_time:.3f}s "
        f"total={time.perf_counter() - total_start:.3f}s",
        flush=True,
    )

    return {
        "result": result_text,
        "source_documents": source_documents,
        "used_rag": True,
    }


suggestions = {
    'ar': {
        "أنواع المنصة": "ما هي أنواع المنصات؟ اشرح لي الأنواع",
        "خطوات الدخول": "ما هي الخطوات لتسجيل الدخول إلى المنصة؟",
        "شروط ومدة العرض": "ما هي القواعد التي يجب اتباعها عند استخدام المنصة؟",
    },
    'en': {
        "Platform Types": "What are the types of JorMall's platform?",
        "Log-in Steps": "What are the steps to log in to the platform?",
        "SMS Conditions and time limit": "What rules and time restrictions should I be aware of when using the platform?",
    },
}
