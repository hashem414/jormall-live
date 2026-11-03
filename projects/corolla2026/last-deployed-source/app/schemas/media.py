from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MediaCollectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    general_description: str = Field(min_length=1, max_length=4000)
    general_description_language: str = Field(default="en", max_length=10)
    retrieval_enabled: bool = True

    @field_validator("*", mode="before")
    @classmethod
    def clean_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class MediaCollectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    general_description: str | None = Field(default=None, min_length=1, max_length=4000)
    general_description_language: str | None = Field(default=None, max_length=10)
    retrieval_enabled: bool | None = None
    is_approved: bool | None = None


class MediaImageMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_title_en: str | None = Field(default=None, max_length=255)
    ai_title_ar: str | None = Field(default=None, max_length=255)
    visual_description_en: str | None = Field(default=None, max_length=4000)
    visual_description_ar: str | None = Field(default=None, max_length=4000)
    alt_text_en: str | None = Field(default=None, max_length=500)
    alt_text_ar: str | None = Field(default=None, max_length=500)
    detected_category: str | None = Field(default=None, max_length=120)
    detected_product_type: str | None = Field(default=None, max_length=120)
    detected_brand: str | None = Field(default=None, max_length=120)
    detected_model: str | None = Field(default=None, max_length=120)
    detected_colour: str | None = Field(default=None, max_length=80)
    detected_view: str | None = Field(default=None, max_length=80)
    detected_image_type: str | None = Field(default=None, max_length=120)
    detected_features: list[str] | None = Field(default=None, max_length=80)
    detected_objects: list[str] | None = Field(default=None, max_length=80)
    visible_text: list[str] | None = Field(default=None, max_length=80)
    dominant_subject: str | None = Field(default=None, max_length=255)
    suggested_group: str | None = Field(default=None, max_length=120)
    keywords_en: list[str] | None = Field(default=None, max_length=80)
    keywords_ar: list[str] | None = Field(default=None, max_length=80)
    needs_review: bool | None = None
    review_reasons: list[str] | None = Field(default=None, max_length=40)
    is_approved: bool | None = None
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0)


class MediaApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    approved_by: str = Field(default="JorMall staff", max_length=120)


class MediaPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=120)
    avoid_image_ids: list[UUID] = Field(default_factory=list, max_length=20)
