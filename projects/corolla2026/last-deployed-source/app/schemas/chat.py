from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatHistoryTurn(BaseModel):
    """
    A single recent conversation turn sent by the browser.

    History helps understand follow-up questions, but it is never treated
    as factual evidence. Approved JorMall documents remain the only source
    for factual answers.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]

    content: str = Field(
        min_length=1,
        max_length=800,
    )

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("History content cannot be empty.")

        return cleaned_value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=1,
        max_length=1000,
    )

    session_id: str | None = Field(
        default=None,
        max_length=120,
    )

    lead_session_id: str | None = Field(
        default=None,
        max_length=120,
    )

    history: list[ChatHistoryTurn] = Field(
        default_factory=list,
        max_length=16,
    )

    evidence_history: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=8,
    )

    starter_action_id: str | None = Field(
        default=None,
        max_length=80,
    )

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("Message cannot be empty.")

        return cleaned_value

    @field_validator("session_id", "lead_session_id")
    @classmethod
    def clean_optional_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned_value = value.strip()

        if not cleaned_value:
            return None

        return cleaned_value

    @field_validator("starter_action_id")
    @classmethod
    def clean_starter_action_id(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned_value = value.strip()
        if not cleaned_value:
            return None

        return cleaned_value


class ChatSourceResponse(BaseModel):
    document_title: str
    section_title: str | None
    source_reference: str | None
    similarity: float


class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    disclaimer: str | None
    model_called: bool
    sources: list[ChatSourceResponse]
