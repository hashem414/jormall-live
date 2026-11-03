import json
import re
from datetime import datetime
from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.constants import DEFAULT_LEAD_CONSENT_VERSION, PILOT_PRECHAT_LEAD_CAPTURE_SLUGS
from app.core.config import settings
from app.core.database import get_db
from app.models.document import ChatConversation, ChatbotLead, ChatbotLeadSession, SalesCallbackRequest
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSourceResponse,
)
from app.services.client_config_service import load_client_config
from app.services.chat_service import (
    ABOUT_JORMALL_ACTION_ID,
    build_chat_result,
    central_ecommerce_about_jormall_answer,
)
from app.services.chat_history_service import record_chat_exchange
from app.services.chat_stream_service import stream_grounded_chat
from app.services.session_memory_store import (
    append_exchange,
    format_history_answer,
    history_for_prompt,
    load_media_context,
    load_product_context,
)


router = APIRouter(
    prefix="/api",
    tags=["Client Chat"],
)


NAME_WORD_PATTERN = re.compile(r"^[^\W\d_]+(?:[-'][^\W\d_]+)*$", flags=re.UNICODE)
JORDANIAN_MOBILE_PATTERN = re.compile(r"^07[0-9]{8}$")


class LeadCapturePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=20)
    company: str | None = Field(default=None, max_length=120)
    cookie_consent_accepted: bool | None = None
    privacy_consent_accepted: bool | None = None

    @field_validator("session_id")
    @classmethod
    def clean_session_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Session ID is required.")
        return cleaned[:120]

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value.strip())
        words = cleaned.split(" ")
        if len(words) < 2 or not all(NAME_WORD_PATTERN.fullmatch(word) for word in words):
            raise ValueError("Please enter your first and last name.")
        return cleaned

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value: str) -> str:
        cleaned = value.strip()
        if not JORDANIAN_MOBILE_PATTERN.fullmatch(cleaned):
            raise ValueError(
                "Please enter a valid 10-digit Jordanian mobile number starting with 07."
            )
        return cleaned

    @field_validator("company")
    @classmethod
    def clean_company(cls, value: str | None) -> str | None:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())[:120]
        return cleaned or None


class SalesCallbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=120)

    @field_validator("session_id")
    @classmethod
    def clean_session_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Session ID is required.")
        return cleaned[:120]


def lead_capture_required(client_slug: str) -> bool:
    if client_slug == "jormall":
        return False
    if client_slug in PILOT_PRECHAT_LEAD_CAPTURE_SLUGS:
        return True
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError:
        return False
    return bool(
        getattr(config, "include_sales_callback_dashboard", True)
        or getattr(config, "include_chat_history_dashboard", True)
    )


def sales_callback_enabled(client_slug: str) -> bool:
    if client_slug == "jormall":
        return False
    if client_slug in PILOT_PRECHAT_LEAD_CAPTURE_SLUGS:
        return True
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError:
        return False
    return bool(getattr(config, "include_sales_callback_dashboard", True))


def normalize_lead_phone(value: str) -> str:
    return value.strip()


def consent_version_for_config(config) -> str:
    return (getattr(config, "lead_consent_version", "") or DEFAULT_LEAD_CONSENT_VERSION).strip()


def get_existing_lead_session(
    *,
    db: Session,
    client_slug: str,
    session_id: str,
) -> ChatbotLeadSession | None:
    return db.scalar(
        select(ChatbotLeadSession).where(
            ChatbotLeadSession.client_slug == client_slug,
            ChatbotLeadSession.session_id == session_id,
        )
    )


def lead_session_has_current_consent(
    session: ChatbotLeadSession | None,
    *,
    consent_version: str,
) -> bool:
    return bool(session and session.lead_id)


def get_existing_lead(*, db: Session, client_slug: str, session_id: str) -> ChatbotLead | None:
    return db.scalar(
        select(ChatbotLead)
        .join(ChatbotLeadSession, ChatbotLeadSession.lead_id == ChatbotLead.id)
        .where(
            ChatbotLead.client_slug == client_slug,
            ChatbotLeadSession.client_slug == client_slug,
            ChatbotLeadSession.session_id == session_id,
        )
    ) or db.scalar(
        select(ChatbotLead).where(
            ChatbotLead.client_slug == client_slug,
            ChatbotLead.session_id == session_id,
        )
    )


def get_existing_lead_by_phone(
    *,
    db: Session,
    client_slug: str,
    phone: str,
) -> ChatbotLead | None:
    return db.scalar(
        select(ChatbotLead).where(
            ChatbotLead.client_slug == client_slug,
            ChatbotLead.normalized_phone == normalize_lead_phone(phone),
        )
    )


def link_lead_session(
    *,
    db: Session,
    lead: ChatbotLead,
    client_slug: str,
    session_id: str,
    consent_version: str | None = None,
) -> ChatbotLeadSession:
    session = get_existing_lead_session(
        db=db,
        client_slug=client_slug,
        session_id=session_id,
    )
    if session is None:
        session = ChatbotLeadSession(
            lead_id=lead.id,
            client_slug=client_slug,
            session_id=session_id,
        )
        db.add(session)
    else:
        session.lead_id = lead.id
        session.last_seen_at = func.now()

    return session


def ensure_lead_capture_completed(
    *,
    db: Session,
    client_slug: str,
    session_id: str | None,
) -> None:
    if not lead_capture_required(client_slug):
        return

    clean_session_id = (session_id or "").strip()[:120]
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Client chatbot not found.") from error

    consent_version = consent_version_for_config(config)
    if clean_session_id and lead_session_has_current_consent(
        get_existing_lead_session(
            db=db,
            client_slug=client_slug,
            session_id=clean_session_id,
        ),
        consent_version=consent_version,
    ):
        return

    raise HTTPException(
        status_code=403,
        detail="Please enter your name and mobile number before starting the chat.",
    )


@router.get(
    "/chat/{client_slug}/lead",
    summary="Check pilot pre-chat lead capture status",
)
def get_chatbot_lead_status(
    client_slug: str,
    session_id: str = "",
    db: Session = Depends(get_db),
):
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Client chatbot not found.") from error

    required = lead_capture_required(client_slug)
    clean_session_id = (session_id or "").strip()[:120]
    consent_version = consent_version_for_config(config)
    lead_session = (
        get_existing_lead_session(
            db=db,
            client_slug=client_slug,
            session_id=clean_session_id,
        )
        if required and clean_session_id
        else None
    )
    captured = bool(
        required
        and clean_session_id
        and lead_session_has_current_consent(
            lead_session,
            consent_version=consent_version,
        )
    )
    return {
        "client_slug": client_slug,
        "required": required,
        "captured": captured,
        "consent_version": consent_version,
    }


@router.post(
    "/chat/{client_slug}/lead",
    summary="Save pilot pre-chat lead capture details",
)
def save_chatbot_lead(
    client_slug: str,
    payload: LeadCapturePayload,
    db: Session = Depends(get_db),
):
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Client chatbot not found.") from error

    if not lead_capture_required(client_slug):
        raise HTTPException(status_code=404, detail="Lead capture is not enabled for this chatbot.")

    lead = get_existing_lead_by_phone(
        db=db,
        client_slug=client_slug,
        phone=payload.phone,
    )
    created = lead is None
    if lead is None:
        lead = ChatbotLead(
            client_slug=client_slug,
            session_id=payload.session_id,
            name=payload.name,
            phone=payload.phone,
            normalized_phone=normalize_lead_phone(payload.phone),
        )
        db.add(lead)
        db.flush()
    else:
        lead.name = payload.name
        lead.phone = payload.phone
        lead.normalized_phone = normalize_lead_phone(payload.phone)
        lead.last_seen_at = func.now()

    link_lead_session(
        db=db,
        lead=lead,
        client_slug=client_slug,
        session_id=payload.session_id,
        consent_version=consent_version_for_config(config),
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        lead = get_existing_lead(
            db=db,
            client_slug=client_slug,
            session_id=payload.session_id,
        ) or get_existing_lead_by_phone(
            db=db,
            client_slug=client_slug,
            phone=payload.phone,
        )
        if lead is None:
            raise HTTPException(
                status_code=409,
                detail="Lead details could not be saved. Please try again.",
            )
        lead.name = payload.name
        lead.phone = payload.phone
        lead.normalized_phone = normalize_lead_phone(payload.phone)
        lead.last_seen_at = func.now()
        link_lead_session(
            db=db,
            lead=lead,
            client_slug=client_slug,
            session_id=payload.session_id,
            consent_version=consent_version_for_config(config),
        )
        created = False
        db.commit()

    db.refresh(lead)
    return {
        "success": True,
        "created": created,
        "client_slug": lead.client_slug,
        "session_id": payload.session_id,
        "lead_id": str(lead.id),
    }


def _legacy_callback_response_message(*, already_pending: bool, language: str) -> str:
    if language == "ar":
        return (
            "تم استلام طلب المكالمة مسبقًا، وسيتواصل معك فريق المبيعات باستخدام رقم الهاتف الذي أدخلته."
            if already_pending
            else "تم استلام طلب المكالمة، وسيتواصل معك فريق المبيعات باستخدام رقم الهاتف الذي أدخلته."
        )

    return (
        "Your call request has already been received. Our sales team will contact you using the mobile number you provided."
        if already_pending
        else "Your call request has been received. Our sales team will contact you using the mobile number you provided."
    )


def callback_response_message(*, already_pending: bool, language: str) -> str:
    if language == "ar":
        return (
            "تم تسجيل طلبك مسبقًا، وسيتواصل معك أحد أعضاء فريق المبيعات."
            if already_pending
            else "تم تسجيل طلبك، وسيتواصل معك أحد أعضاء فريق المبيعات."
        )

    return (
        "Your request has already been recorded. A member of the sales team will contact you."
        if already_pending
        else "Your request has been recorded. A member of the sales team will contact you."
    )


@router.post(
    "/chat/{client_slug}/request-sales-call",
    summary="Request a sales callback for the pilot chatbot",
)
def request_sales_call(
    client_slug: str,
    payload: SalesCallbackPayload,
    language: str = "en",
    db: Session = Depends(get_db),
):
    if not sales_callback_enabled(client_slug):
        raise HTTPException(status_code=404, detail="Sales callback is not enabled for this chatbot.")

    ensure_lead_capture_completed(
        db=db,
        client_slug=client_slug,
        session_id=payload.session_id,
    )

    lead = get_existing_lead(
        db=db,
        client_slug=client_slug,
        session_id=payload.session_id,
    )
    if lead is None:
        raise HTTPException(
            status_code=403,
            detail="Please enter your name and mobile number before requesting a call.",
        )

    existing_pending = db.scalar(
        select(SalesCallbackRequest).where(
            SalesCallbackRequest.client_slug == client_slug,
            SalesCallbackRequest.lead_id == lead.id,
            SalesCallbackRequest.status == "pending",
        )
    )
    conversation = db.scalar(
        select(ChatConversation)
        .where(
            ChatConversation.client_slug == client_slug,
            or_(
                ChatConversation.session_id == payload.session_id,
                ChatConversation.lead_session_id == payload.session_id,
            ),
        )
        .order_by(ChatConversation.last_message_at.desc())
        .limit(1)
    )
    already_pending = existing_pending is not None

    if existing_pending is None:
        callback_request = SalesCallbackRequest(
            client_slug=client_slug,
            lead_id=lead.id,
            session_id=payload.session_id,
            conversation_id=conversation.id if conversation is not None else None,
            status="pending",
        )
        db.add(callback_request)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            already_pending = True
            existing_pending = db.scalar(
                select(SalesCallbackRequest).where(
                    SalesCallbackRequest.client_slug == client_slug,
                    SalesCallbackRequest.lead_id == lead.id,
                    SalesCallbackRequest.status == "pending",
                )
            )
            if existing_pending is None:
                raise HTTPException(
                    status_code=409,
                    detail="Call request could not be saved. Please try again.",
                )
        else:
            existing_pending = callback_request
    elif conversation is not None and existing_pending.conversation_id is None:
        existing_pending.conversation_id = conversation.id
        db.commit()

    return {
        "success": True,
        "already_pending": already_pending,
        "message": callback_response_message(
            already_pending=already_pending,
            language="ar" if language == "ar" else "en",
        ),
        "request_id": str(existing_pending.id) if existing_pending is not None else "",
        "status": "pending",
    }


def require_callback_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    supplied = (x_admin_token or "").strip()
    if not supplied:
        raise HTTPException(status_code=401, detail="Admin token is required.")

    configured_secret = settings.callback_admin_token
    configured = configured_secret.get_secret_value() if configured_secret else ""
    if not configured:
        raise HTTPException(status_code=503, detail="Callback admin token is not configured.")

    if not compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Admin token is required.")


def callback_requests_query(
    *,
    db: Session,
    client_slug: str,
    status: str,
    date_from: str,
    date_to: str,
):
    statement = (
        select(SalesCallbackRequest, ChatbotLead)
        .join(ChatbotLead, ChatbotLead.id == SalesCallbackRequest.lead_id)
        .order_by(SalesCallbackRequest.requested_at.desc())
    )

    if client_slug:
        statement = statement.where(SalesCallbackRequest.client_slug == client_slug)

    if status:
        statement = statement.where(SalesCallbackRequest.status == status)

    if date_from:
        try:
            parsed_from = datetime.fromisoformat(date_from)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid date_from.") from error
        statement = statement.where(SalesCallbackRequest.requested_at >= parsed_from)

    if date_to:
        try:
            parsed_to = datetime.fromisoformat(date_to)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid date_to.") from error
        statement = statement.where(SalesCallbackRequest.requested_at <= parsed_to)

    return db.execute(statement).all()


@router.get(
    "/admin/sales-callback-requests",
    summary="List sales callback requests",
)
def list_sales_callback_requests(
    client_slug: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    _: None = Depends(require_callback_admin_token),
    db: Session = Depends(get_db),
):
    rows = callback_requests_query(
        db=db,
        client_slug=client_slug,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "total": len(rows),
        "requests": [
            {
                "id": str(callback.id),
                "client_slug": callback.client_slug,
                "lead_id": str(lead.id),
                "name": lead.name,
                "phone": lead.phone,
                "session_id": callback.session_id,
                "status": callback.status,
                "requested_at": callback.requested_at.isoformat(),
                "contacted_at": callback.contacted_at.isoformat()
                if callback.contacted_at
                else "",
            }
            for callback, lead in rows
        ],
    }


@router.get(
    "/admin/sales-callback-requests/export.csv",
    summary="Export sales callback requests as CSV",
)
def export_sales_callback_requests(
    client_slug: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    _: None = Depends(require_callback_admin_token),
    db: Session = Depends(get_db),
):
    import csv
    from io import StringIO

    rows = callback_requests_query(
        db=db,
        client_slug=client_slug,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Phone", "Requested At", "Status", "Contacted At", "Client", "Session ID"])
    for callback, lead in rows:
        writer.writerow(
            [
                lead.name,
                lead.phone,
                callback.requested_at.isoformat(),
                callback.status,
                callback.contacted_at.isoformat() if callback.contacted_at else "",
                callback.client_slug,
                callback.session_id,
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=callback_requests.csv"},
    )


def update_streamed_answer(current_answer: str, line: str) -> str:
    try:
        event = json.loads(line)
    except Exception:
        return current_answer

    event_type = event.get("type")

    if event_type == "replace":
        return str(event.get("answer") or "")

    if event_type == "delta":
        return current_answer + str(event.get("text") or "")

    if event_type == "error":
        return ""

    return current_answer


def product_references_from_stream_line(line: str) -> list[dict] | None:
    try:
        event = json.loads(line)
    except Exception:
        return None
    references = event.get("product_references")
    if isinstance(references, list):
        return [reference for reference in references if isinstance(reference, dict)]
    return None


def media_context_from_stream_line(line: str) -> dict | None:
    try:
        event = json.loads(line)
    except Exception:
        return None
    context = event.get("media_context")
    return context if isinstance(context, dict) else None


def encode_event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def yield_direct_answer(answer: str):
    yield encode_event(
        {
            "type": "replace",
            "answer": answer,
            "grounded": True,
            "conversation_memory": True,
            "disclaimer": None,
            "sources": [],
            "media": [],
        }
    )
    yield encode_event(
        {
            "type": "done",
            "grounded": True,
            "conversation_memory": True,
            "model_called": False,
        }
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask the JorMall Document Assistant",
)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    try:
        result = build_chat_result(
            question=payload.message,
            db=db,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "The JorMall assistant is temporarily unavailable. "
                "Please try again later."
            ),
        ) from error

    return ChatResponse(
        answer=result.answer,
        grounded=result.grounded,
        disclaimer=result.disclaimer,
        model_called=result.model_called,
        sources=[
            ChatSourceResponse(
                document_title=source.document_title,
                section_title=source.section_title,
                source_reference=source.source_reference,
                similarity=source.similarity,
            )
            for source in result.sources
        ],
    )


@router.post(
    "/chat/stream",
    summary="Stream a grounded JorMall answer",
)
def stream_chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    def event_generator():
        answer_text = ""
        product_references = None
        media_context = None
        last_product_reference, last_product_references = load_product_context(
            client_slug="jormall",
            session_id=payload.session_id,
        )
        last_media_context = load_media_context(
            client_slug="jormall",
            session_id=payload.session_id,
        )
        history_answer = format_history_answer(
            request_message=payload.message,
            client_slug="jormall",
            session_id=payload.session_id,
            frontend_history=payload.history,
        )

        if history_answer is not None:
            yield from yield_direct_answer(history_answer)
            append_exchange(
                client_slug="jormall",
                session_id=payload.session_id,
                user_message=payload.message,
                assistant_message=history_answer,
            )
            record_chat_exchange(
                db=db,
                client_slug="jormall",
                session_id=payload.session_id,
                lead_session_id=payload.lead_session_id,
                user_message=payload.message,
                assistant_message=history_answer,
            )
            return

        prompt_history = history_for_prompt(
            client_slug="jormall",
            session_id=payload.session_id,
            frontend_history=payload.history,
        )

        for line in stream_grounded_chat(
            question=payload.message,
            history=prompt_history,
            evidence_history=payload.evidence_history,
            db=db,
            last_product_reference=last_product_reference,
            last_product_references=last_product_references,
            last_media_context=last_media_context,
        ):
            answer_text = update_streamed_answer(answer_text, line)
            streamed_references = product_references_from_stream_line(line)
            if streamed_references is not None:
                product_references = streamed_references
            streamed_media_context = media_context_from_stream_line(line)
            if streamed_media_context is not None:
                media_context = streamed_media_context
            yield line

        if answer_text.strip():
            append_exchange(
                client_slug="jormall",
                session_id=payload.session_id,
                user_message=payload.message,
                assistant_message=answer_text,
                product_references=product_references,
                media_context=media_context,
            )
            record_chat_exchange(
                db=db,
                client_slug="jormall",
                session_id=payload.session_id,
                lead_session_id=payload.lead_session_id,
                user_message=payload.message,
                assistant_message=answer_text,
                media_context=media_context,
            )

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/chat/{client_slug}/stream",
    summary="Stream a grounded client-specific answer",
)
def stream_client_chat(
    client_slug: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Client chatbot not found.",
        ) from error
    ensure_lead_capture_completed(
        db=db,
        client_slug=client_slug,
        session_id=payload.lead_session_id or payload.session_id,
    )

    def event_generator():
        answer_text = ""
        product_references = None
        media_context = None
        last_product_reference, last_product_references = load_product_context(
            client_slug=client_slug,
            session_id=payload.session_id,
        )
        last_media_context = load_media_context(
            client_slug=client_slug,
            session_id=payload.session_id,
        )
        history_answer = format_history_answer(
            request_message=payload.message,
            client_slug=client_slug,
            session_id=payload.session_id,
            frontend_history=payload.history,
        )

        if history_answer is not None:
            yield from yield_direct_answer(history_answer)
            append_exchange(
                client_slug=client_slug,
                session_id=payload.session_id,
                user_message=payload.message,
                assistant_message=history_answer,
            )
            record_chat_exchange(
                db=db,
                client_slug=client_slug,
                session_id=payload.session_id,
                lead_session_id=payload.lead_session_id,
                user_message=payload.message,
                assistant_message=history_answer,
            )
            return

        if payload.starter_action_id == ABOUT_JORMALL_ACTION_ID:
            about_answer = central_ecommerce_about_jormall_answer(
                question=payload.message,
                config=config,
                starter_action_id=payload.starter_action_id,
            )
            if about_answer is not None:
                yield from yield_direct_answer(about_answer)
                append_exchange(
                    client_slug=client_slug,
                    session_id=payload.session_id,
                    user_message=payload.message,
                    assistant_message=about_answer,
                )
                record_chat_exchange(
                    db=db,
                    client_slug=client_slug,
                    session_id=payload.session_id,
                    lead_session_id=payload.lead_session_id,
                    user_message=payload.message,
                    assistant_message=about_answer,
                )
                return

        prompt_history = history_for_prompt(
            client_slug=client_slug,
            session_id=payload.session_id,
            frontend_history=payload.history,
        )

        for line in stream_grounded_chat(
            question=payload.message,
            history=prompt_history,
            evidence_history=payload.evidence_history,
            db=db,
            client_slug=client_slug,
            last_product_reference=last_product_reference,
            last_product_references=last_product_references,
            last_media_context=last_media_context,
        ):
            answer_text = update_streamed_answer(answer_text, line)
            streamed_references = product_references_from_stream_line(line)
            if streamed_references is not None:
                product_references = streamed_references
            streamed_media_context = media_context_from_stream_line(line)
            if streamed_media_context is not None:
                media_context = streamed_media_context
            yield line

        if answer_text.strip():
            append_exchange(
                client_slug=client_slug,
                session_id=payload.session_id,
                user_message=payload.message,
                assistant_message=answer_text,
                product_references=product_references,
                media_context=media_context,
            )
            record_chat_exchange(
                db=db,
                client_slug=client_slug,
                session_id=payload.session_id,
                lead_session_id=payload.lead_session_id,
                user_message=payload.message,
                assistant_message=answer_text,
                media_context=media_context,
            )

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
