from __future__ import annotations

import json
from typing import Literal

from openai import OpenAIError
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.chat import ChatHistoryTurn
from app.services.openai_client import get_openai_client


MAX_RECENT_TURNS = 16
MAX_TURN_CHARACTERS = 1200


class ConversationTurnForBrain(BaseModel):
    index: int
    role: Literal["user", "assistant"]
    content: str


class ConversationBrainDecision(BaseModel):
    """
    Decides whether the latest message needs conversation memory,
    client document retrieval, or clarification.
    """

    route: Literal[
        "answer_from_memory",
        "retrieve_documents",
        "clarify",
    ]

    intent: Literal[
        "chat_summary",
        "full_conversation",
        "conversation_qa",
        "last_question",
        "last_answer",
        "repeat_previous_answer",
        "new_client_question",
        "follow_up_client_question",
        "ambiguous_reference",
        "general_non_client",
    ]

    language: Literal["en", "ar", "mixed", "unknown"] = "unknown"

    memory_answer: str = Field(
        default="",
        max_length=2500,
        description=(
            "Answer using only the supplied conversation JSON. "
            "Used only when route is answer_from_memory."
        ),
    )

    standalone_question: str = Field(
        default="",
        max_length=1200,
        description=(
            "A rewritten standalone client question for retrieval. "
            "Used only when route is retrieve_documents."
        ),
    )

    retrieval_query: str = Field(
        default="",
        max_length=1200,
        description=(
            "A concise client-aware search query optimized for vector retrieval. "
            "Used only when route is retrieve_documents."
        ),
    )

    clarifying_question: str = Field(
        default="",
        max_length=500,
        description=(
            "A short question asking the user what they mean. "
            "Used only when route is clarify."
        ),
    )

    referenced_turn_indexes: list[int] = Field(
        default_factory=list,
        max_length=16,
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


def trim_text(text: str, max_characters: int = MAX_TURN_CHARACTERS) -> str:
    clean_text = text.strip()

    if len(clean_text) <= max_characters:
        return clean_text

    return clean_text[: max_characters - 20].rstrip() + " ...[trimmed]"


def get_recent_history(
    history: list[ChatHistoryTurn],
) -> list[ChatHistoryTurn]:
    return history[-MAX_RECENT_TURNS:]


def build_conversation_json(
    *,
    question: str,
    history: list[ChatHistoryTurn],
    client_name: str,
    client_slug: str,
    assistant_name: str | None = None,
) -> str:
    recent_history = get_recent_history(history)

    turns: list[ConversationTurnForBrain] = []

    for index, turn in enumerate(recent_history):
        turns.append(
            ConversationTurnForBrain(
                index=index,
                role=turn.role,
                content=trim_text(turn.content),
            )
        )

    payload = {
        "assistant_name": assistant_name or f"{client_name} Assistant",
        "client_name": client_name,
        "client_slug": client_slug,
        "core_rule": (
            "Conversation memory is only used to understand and summarize the current chat. "
            f"It is not an official source for {client_name} business facts."
        ),
        "source_rules": {
            "conversation_memory_can_answer": [
                "summaries of this chat",
                "the full conversation",
                "question and answer transcript",
                "last question",
                "last answer",
                "repeat what the assistant already said",
            ],
            "approved_documents_must_answer": [
                f"{client_name} services",
                f"{client_name} prices",
                f"{client_name} discounts or offers",
                f"{client_name} working hours",
                f"{client_name} location or address",
                f"{client_name} contact details",
                f"{client_name} policies",
                f"{client_name} website content",
                "company information",
                "uploaded document facts",
            ],
        },
        "recent_conversation_oldest_first": [
            turn.model_dump()
            for turn in turns
        ],
        "current_user_message": question,
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def build_brain_instructions(
    *,
    client_name: str,
) -> str:
    return f"""
You are the Conversation Brain for {client_name} Document Assistant.

Your job is to decide how to handle the user's latest message using the supplied conversation JSON.

You must choose exactly one route:

1. answer_from_memory

Use this when the user is asking about the current chat itself, such as:
- summary of the whole chat
- full conversation
- conversation Q&A
- what did I ask
- what did you answer
- repeat your answer
- summarize what we discussed

For answer_from_memory:
- Write memory_answer directly from the conversation JSON.
- Do not use {client_name} business knowledge.
- Do not retrieve documents.
- Do not invent any messages that are not in the conversation JSON.
- Keep the same language as the user's request where possible.

2. retrieve_documents

Use this when the user is asking about {client_name} facts, policies, services, pricing, website content, working hours, location, contact details, or anything that should be answered from approved company documents.

Also use retrieve_documents for factual follow-ups such as:
- what about that service?
- explain the third requirement
- what does that include?
- where are you located?
- how can I contact you?
- what are your working hours?

For retrieve_documents:
- Do not answer the question.
- Use conversation JSON only to resolve references such as "it", "that", "the third one", or "the previous service".
- Write a clear standalone_question.
- Write a concise retrieval_query for vector search.
- For generic questions like "What services do you provide?", "How can I contact you?", or "Where are you located?", keep the current client in mind and use {client_name} in the retrieval query when useful.
- Never rewrite a non-JorMall client's question into a JorMall question.
- Preserve the user's language where possible.

3. clarify

Use this only when the user's message refers to something unclear and you cannot determine whether it is a memory request or a {client_name} document question.

Important:
- Never suggest follow-up questions.
- Never include text outside the structured output.
- Never treat conversation memory as official {client_name} business truth.
- {client_name} facts must always go through retrieve_documents.
""".strip()


def fallback_decision(question: str) -> ConversationBrainDecision:
    return ConversationBrainDecision(
        route="retrieve_documents",
        intent="new_client_question",
        language="unknown",
        memory_answer="",
        standalone_question=question,
        retrieval_query=question,
        clarifying_question="",
        referenced_turn_indexes=[],
        confidence=0.0,
    )


def resolve_conversation_intent(
    *,
    question: str,
    history: list[ChatHistoryTurn],
    client_name: str,
    client_slug: str,
    assistant_name: str | None = None,
) -> ConversationBrainDecision:
    """
    Uses GPT as a small conversation router.

    It is never used as the factual source for client business answers.
    """

    if not history:
        return ConversationBrainDecision(
            route="retrieve_documents",
            intent="new_client_question",
            language="unknown",
            memory_answer="",
            standalone_question=question,
            retrieval_query=question,
            clarifying_question="",
            referenced_turn_indexes=[],
            confidence=1.0,
        )

    try:
        response = get_openai_client().responses.parse(
            model=settings.openai_chat_model,
            reasoning={
                "effort": settings.chat_reasoning_effort,
            },
            text={
                "verbosity": "low",
            },
            instructions=build_brain_instructions(
                client_name=client_name,
            ),
            input=build_conversation_json(
                question=question,
                history=history,
                client_name=client_name,
                client_slug=client_slug,
                assistant_name=assistant_name,
            ),
            text_format=ConversationBrainDecision,
            max_output_tokens=800,
            store=False,
        )

    except OpenAIError:
        return fallback_decision(question)

    if response.output_parsed is None:
        return fallback_decision(question)

    decision = (
        response.output_parsed
        if isinstance(response.output_parsed, ConversationBrainDecision)
        else ConversationBrainDecision.model_validate(response.output_parsed)
    )

    if decision.route == "answer_from_memory":
        if not decision.memory_answer.strip():
            return ConversationBrainDecision(
                route="clarify",
                intent="ambiguous_reference",
                language=decision.language,
                memory_answer="",
                standalone_question="",
                retrieval_query="",
                clarifying_question=(
                    "I can summarize the current chat, but I do not have enough saved conversation history yet."
                ),
                referenced_turn_indexes=[],
                confidence=0.3,
            )

        decision.standalone_question = ""
        decision.retrieval_query = ""
        decision.clarifying_question = ""
        return decision

    if decision.route == "retrieve_documents":
        if not decision.standalone_question.strip():
            decision.standalone_question = question

        if not decision.retrieval_query.strip():
            decision.retrieval_query = decision.standalone_question

        decision.memory_answer = ""
        decision.clarifying_question = ""
        return decision

    if decision.route == "clarify":
        if not decision.clarifying_question.strip():
            decision.clarifying_question = (
                "Can you clarify what you are referring to?"
            )

        decision.memory_answer = ""
        decision.standalone_question = ""
        decision.retrieval_query = ""
        return decision

    return fallback_decision(question)
