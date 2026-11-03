"""
محرّك المحادثة — الطبقة اللي بتربط كل شي.

المسار الكامل لكل رسالة:
  رسالة العميل
     ↓ (1) كشف اللغة + تحميل سجل المحادثة من PostgreSQL
     ↓ (2) إعادة صياغة السؤال ليصير مستقلاً عن السياق (Query Condensation)
     ↓ (3) بحث هجين: دلالي (pgvector) + كلمات مفتاحية (tsvector) → دمج RRF
     ↓ (4) بناء البرومبت: الدستور السلوكي + السياق المسترجع + السجل
     ↓ (5) استدعاء OpenAI مع الأدوات، وتنفيذ أي أداة يطلبها الموديل
     ↓ (6) حفظ الرسالة والرد ومصادر الاسترجاع للتدقيق
  الرد
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from .clients import get_openai
from .config import get_settings
from .memory import (
    add_message,
    conversation_has_recent_appointment,
    format_history,
    open_conversation,
)
from .prompts import CONDENSE_PROMPT, build_system_prompt
from .retrieval import RetrievedChunk, build_context, retrieve
from .text_utils import detect_language
from .tools import TOOL_SCHEMAS, execute_tool

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 3

# أدوات بتنفّذ بآخر الدور: نتيجتها إضافة للرد، مش موضوعه، ولازم تعرف
# شو صار قبلها بنفس الدور حتى ما تزيح تعليمة أهم منها.
_DEFERRED_TOOLS = {"send_location"}

# ══════ حارس التأكيد الكاذب ══════
# الموديل كان يكتب «تم تسجيل طلبك لموعد …» بدون ما يستدعي `book_appointment` —
# ولا حتى يطلب الاسم والرقم. النتيجة: العميل بيصدّق إنه محجوز، والاستقبال ما بيشوف
# شي، وبيجي ع العيادة بيوم ما إله موعد فيه. جرّبنا منعها بالتعليمات ثلاث مرات وما
# نفعت، فصارت فحصاً بالكود: أي رد بيدّعي حجزاً بدون صف بقاعدة البيانات بينستبدل.
_BOOKING_CLAIM = re.compile(
    r"تم\s+تسجيل\s+(طلب|موعد)|تم\s+حجز|حجزتلك|سجّلتلك|سجلتلك|انسجّل\s+موعد"
    r"|موعدك\s+(مثبّت|مثبت|محجوز|مسجّل|مسجل)"
    r"|has\s+been\s+(recorded|booked|registered|scheduled)"
    r"|i(?:'ve|\s+have)\s+(booked|registered|recorded)"
    r"|your\s+(appointment|booking|request)\s+is\s+(booked|registered|recorded|confirmed)",
    re.IGNORECASE,
)
# نفي صريح = مش ادّعاء («ما تم تسجيل موعدك»، "has not been recorded")
_CLAIM_NEGATED = re.compile(
    r"ما\s+تم|لم\s+يتم|ما\s+قدرت|مش\s+قادر"
    r"|not\s+been|couldn'?t|could\s+not|unable\s+to|was\s+not",
    re.IGNORECASE,
)

_UNBOOKED = {
    "ar": (
        "لحظة — لسا ما ثبّتّ الموعد، بعتذر عن اللبس. "
        "عشان أسجّل الطلب بحتاج **اسمك الكامل ورقم موبايلك** بنفس الرسالة. "
        "اكتبهملي ومنكمّل فوراً."
    ),
    "en": (
        "One moment — the appointment is not registered yet, sorry for the confusion. "
        "To record the request I need your **full name and phone number** in one message. "
        "Send them over and we'll finish right away."
    ),
}


def _claims_booking(answer: str) -> bool:
    return bool(_BOOKING_CLAIM.search(answer)) and not _CLAIM_NEGATED.search(answer)


_FALLBACK = {
    "ar": (
        "بعتذر، ما عندي تفاصيل دقيقة عن هالنقطة. فريق الاستقبال بقدر يجاوبك عليها بالضبط — "
        "بتحب تعطيني اسمك الكامل ورقمك ليتواصلوا معك؟"
    ),
    "en": (
        "I'm sorry, I don't have exact details on that. Our reception team can answer precisely — "
        "may I take your full name and phone number so they can call you?"
    ),
}


@dataclass
class ChatResult:
    answer: str
    session_id: str
    lang: str
    search_query: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    grounded: bool = True

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "session_id": self.session_id,
            "lang": self.lang,
            "search_query": self.search_query,
            "grounded": self.grounded,
            "tool_calls": self.tool_calls,
            "sources": [
                {
                    "id": s.id,
                    "breadcrumb": s.breadcrumb,
                    "type": s.chunk_type,
                    "score": round(s.vector_score, 4),
                }
                for s in self.sources
            ],
        }


def _condense(question: str, history: list[dict]) -> str:
    """يحوّل «وهاي كم سعرها؟» لسؤال مستقل قابل للبحث."""
    if not history:
        return question

    settings = get_settings()
    try:
        response = get_openai().chat.completions.create(
            model=settings.utility_model,
            temperature=0,
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": CONDENSE_PROMPT.format(
                        history=format_history(history), question=question
                    ),
                }
            ],
        )
        condensed = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("condense فشل، بنستخدم السؤال الأصلي: %s", exc)
        return question

    if not condensed or condensed.upper().startswith("NONE"):
        return ""  # تحية/شكر/اسم/رقم → ما بدها بحث
    return condensed


def chat(
    message: str,
    *,
    session_id: str,
    channel: str = "web",
    lang: str | None = None,
) -> ChatResult:
    settings = get_settings()
    message = (message or "").strip()
    if not message:
        raise ValueError("الرسالة فاضية")

    # لو المستخدم ضاغط زر اللغة بالواجهة بنحترم اختياره، وإلا بنكشفها من نص الرسالة
    lang = lang if lang in {"ar", "en"} else detect_language(message)
    conversation_id, history = open_conversation(
        session_id, channel=channel, lang=lang, turns=settings.history_turns
    )

    # (2) إعادة صياغة + (3) استرجاع
    search_query = _condense(message, history)
    chunks: list[RetrievedChunk] = retrieve(search_query) if search_query else []
    context = build_context(chunks)

    # (4) بناء الرسائل
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt(context, lang=lang)},
        *history,
        {"role": "user", "content": message},
    ]

    add_message(conversation_id, "user", message, metadata={"channel": channel})

    # (5) استدعاء الموديل + حلقة الأدوات
    client = get_openai()
    executed_tools: list[dict] = []
    # أسماء الأدوات اللي نجحت بهذا الدور — بتنمرّر للأداة اللي بعدها عشان
    # تعرف سياقها (مثلاً: الموقع ما بيزيح تأكيد الحجز لما ينستدعوا سوا)
    succeeded_this_turn: set[str] = set()
    answer = ""

    for _round in range(_MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,  # type: ignore[arg-type]
            tools=TOOL_SCHEMAS,  # type: ignore[arg-type]
            tool_choice="auto",
            temperature=0.3,          # منخفضة = التزام أعلى بالمصدر
            max_tokens=600,
        )
        choice = response.choices[0].message

        if not choice.tool_calls:
            answer = (choice.content or "").strip()
            break

        messages.append(
            {
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in choice.tool_calls
                ],
            }
        )

        # ترتيب تنفيذ ثابت: الأدوات اللي بتغيّر حالة (حجز/إلغاء) بتنفّذ قبل
        # الأدوات العرضية زي `send_location`. الموديل بيبعت الاستدعاءات بأي
        # ترتيب، ولو الموقع انفّذ أول ما بيعرف إنه في حجز بنفس الدور فبتضيع
        # تعليمة «التأكيد أولاً» — والعميل بيشوف عنواناً بدل تأكيد موعده.
        for tool_call in sorted(
            choice.tool_calls, key=lambda c: c.function.name in _DEFERRED_TOOLS
        ):
            result = execute_tool(
                tool_call.function.name,
                tool_call.function.arguments,
                conversation_id,
                user_message=message,   # للتحقق إن بيانات التواصل من رسالة العميل الحالية
                turn_tools=succeeded_this_turn,
            )
            if result.get("ok"):
                succeeded_this_turn.add(tool_call.function.name)
            executed_tools.append(
                {"name": tool_call.function.name, "arguments": tool_call.function.arguments, "result": result}
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        logger.warning("تجاوزنا الحد الأقصى لجولات الأدوات")

    if not answer:
        answer = _FALLBACK[lang]

    # حارس التأكيد الكاذب: ما بنسمح لرد يقول «تم تسجيل موعدك» وما في موعد فعلاً.
    # بنفحص قاعدة البيانات مش بس أدوات هذا الدور، عشان الحجز اللي صار برسالة
    # سابقة بنفس المحادثة يضل تأكيده مشروعاً.
    if "book_appointment" not in succeeded_this_turn and _claims_booking(answer):
        if not conversation_has_recent_appointment(conversation_id):
            logger.error(
                "رد ادّعى حجزاً بدون موعد بقاعدة البيانات — تم استبداله | conversation=%s | %r",
                conversation_id, answer[:160],
            )
            answer = _UNBOOKED[lang]

    add_message(
        conversation_id,
        "assistant",
        answer,
        retrieved_ids=[c.id for c in chunks],
        metadata={"tools": [t["name"] for t in executed_tools], "query": search_query},
    )

    return ChatResult(
        answer=answer,
        session_id=session_id,
        lang=lang,
        search_query=search_query,
        sources=chunks,
        tool_calls=executed_tools,
        grounded=bool(chunks),
    )
