from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import public_chat_shared as shared
from app.core.database import get_db
from app.schemas.chat import ChatRequest


router = APIRouter(tags=["Public Chat"])
CLIENT_SLUG = os.getenv("CLIENT_SLUG", os.getenv("STANDALONE_CLIENT_SLUG", "central-trade-auto-co-markazia-toyota-jordan")).strip() or "central-trade-auto-co-markazia-toyota-jordan"

if CLIENT_SLUG != "central-trade-auto-co-markazia-toyota-jordan":
    raise RuntimeError("CLIENT_SLUG/STANDALONE_CLIENT_SLUG does not match this exported chatbot package.")


def target_client_slug() -> str:
    return CLIENT_SLUG


@router.get("/api/chat/lead")
def get_chatbot_lead_status(session_id: str = "", db: Session = Depends(get_db)):
    return shared.get_chatbot_lead_status(
        client_slug=target_client_slug(),
        session_id=session_id,
        db=db,
    )


@router.post("/api/chat/lead")
def save_chatbot_lead(payload: shared.LeadCapturePayload, db: Session = Depends(get_db)):
    return shared.save_chatbot_lead(
        client_slug=target_client_slug(),
        payload=payload,
        db=db,
    )


@router.post("/api/chat/request-sales-call")
def request_sales_call(
    payload: shared.SalesCallbackPayload,
    language: str = "en",
    db: Session = Depends(get_db),
):
    return shared.request_sales_call(
        client_slug=target_client_slug(),
        payload=payload,
        language=language,
        db=db,
    )


@router.post("/api/chat/stream")
def stream_client_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    return shared.stream_client_chat(
        client_slug=target_client_slug(),
        payload=payload,
        db=db,
    )
