import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.constants import DEFAULT_LEAD_CONSENT_VERSION, PILOT_PRECHAT_LEAD_CAPTURE_SLUGS
from app.core.database import get_db
from app.models.document import ChatbotLead, ChatbotLeadSession, SalesCallbackRequest
from app.schemas.chat import ChatRequest
from app.services.client_config_service import load_client_config
from app.services.chat_service import (
    ABOUT_JORMALL_ACTION_ID,
    central_ecommerce_about_jormall_answer,
    question_requests_comprehensive_answer,
)
from app.services.chat_stream_service import stream_grounded_chat
from app.services.answer_safety_service import business_generation_fallback
from app.services.conversation_store import (
    save_assistant_message,
    save_customer_message,
    ensure_conversation,
)
from app.services.session_memory_store import (
    append_exchange,
    format_history_answer,
    history_for_prompt,
    load_product_context,
)
from app.services.soniox_speech_service import (
    SUPPORTED_AUDIO_TYPES,
    SonioxConfigurationError,
    SonioxSpeechError,
    normalize_audio_content_type,
    prepare_soniox_speech,
    soniox_voice_provider_name,
    stream_soniox_speech,
    transcribe_soniox_audio,
)
from app.core.config import settings
router = APIRouter(
    prefix="/api",
    tags=["Client Chat"],
)


NAME_WORD_PATTERN = re.compile(r"^[^\W\d_]+(?:[-'][^\W\d_]+)*$", flags=re.UNICODE)
JORDANIAN_MOBILE_PATTERN = re.compile(r"^07[0-9]{8}$")
TARGET_CLIENT_SLUG = "central-e-commerce-co-ltd"


def enforce_target_client_slug(client_slug: str) -> None:
    if client_slug != TARGET_CLIENT_SLUG:
        raise HTTPException(status_code=404, detail="Client chatbot not found.")


class LeadCapturePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(min_length=1, max_length=120)
    chat_session_id: str | None = Field(default=None, max_length=120)
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=20)
    cookie_consent_accepted: bool | None = None
    privacy_consent_accepted: bool | None = None
    cookie_notice_opened: bool = False
    privacy_notice_opened: bool = False

    @field_validator("session_id")
    @classmethod
    def clean_session_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Session ID is required.")
        return cleaned[:120]

    @field_validator("chat_session_id")
    @classmethod
    def clean_chat_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned[:120] if cleaned else None

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


class VoiceTranscriptionResponse(BaseModel):
    transcript: str
    confidence: float
    language: str
    provider_language: str


class VoiceSpeechPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1400)
    language: str = Field(pattern=r"^(?:ar|en)$")
    lead_session_id: str = Field(min_length=1, max_length=120)

    @field_validator("text", "lead_session_id")
    @classmethod
    def clean_voice_value(cls, value: str) -> str:
        return value.strip()


def lead_capture_required(client_slug: str) -> bool:
    return client_slug in PILOT_PRECHAT_LEAD_CAPTURE_SLUGS


def normalize_lead_phone(value: str) -> str:
    return value.strip()


def consent_version_for_config(config) -> str:
    return (getattr(config, "lead_consent_version", "") or DEFAULT_LEAD_CONSENT_VERSION).strip()


def prechat_legal_mode_for_config(config) -> str:
    mode = (getattr(config, "prechat_legal_mode", "") or "explicit_consent").strip()
    return mode if mode in {"explicit_consent", "notice_only"} else "explicit_consent"


def notice_version_for_config(config) -> str:
    configured = (getattr(config, "lead_notice_version", "") or "").strip()
    return configured or consent_version_for_config(config)


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
    return bool(
        session
        and session.cookie_consent_accepted
        and session.privacy_consent_accepted
        and session.consent_version == consent_version
        and session.consent_accepted_at is not None
    )


def lead_session_has_current_notice(
    session: ChatbotLeadSession | None,
    *,
    notice_version: str,
) -> bool:
    return bool(
        session
        and session.notice_version == notice_version
        and session.notice_presented_at is not None
    )


def lead_session_completed(
    session: ChatbotLeadSession | None,
    *,
    config,
) -> bool:
    if prechat_legal_mode_for_config(config) == "notice_only":
        return lead_session_has_current_notice(
            session,
            notice_version=notice_version_for_config(config),
        )
    return lead_session_has_current_consent(
        session,
        consent_version=consent_version_for_config(config),
    )


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
    notice_version: str | None = None,
    cookie_notice_opened: bool = False,
    privacy_notice_opened: bool = False,
    processing_basis: str | None = None,
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

    if consent_version:
        session.cookie_consent_accepted = True
        session.privacy_consent_accepted = True
        session.consent_version = consent_version
        session.consent_accepted_at = datetime.now(timezone.utc)
    if notice_version:
        now = datetime.now(timezone.utc)
        session.notice_version = notice_version
        session.notice_presented_at = now
        if cookie_notice_opened:
            session.cookie_notice_opened_at = now
        if privacy_notice_opened:
            session.privacy_notice_opened_at = now
        session.processing_basis = processing_basis
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

    if clean_session_id and lead_session_completed(
        get_existing_lead_session(
            db=db,
            client_slug=client_slug,
            session_id=clean_session_id,
        ),
        config=config,
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
    enforce_target_client_slug(client_slug)
    try:
        config = load_client_config(client_slug)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="Client chatbot not found.") from error

    required = lead_capture_required(client_slug)
    clean_session_id = (session_id or "").strip()[:120]
    consent_version = consent_version_for_config(config)
    notice_version = notice_version_for_config(config)
    legal_mode = prechat_legal_mode_for_config(config)
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
        and lead_session_completed(
            lead_session,
            config=config,
        )
    )
    return {
        "client_slug": client_slug,
        "required": required,
        "captured": captured,
        "legal_mode": legal_mode,
        "consent_version": consent_version,
        "notice_version": notice_version,
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
    enforce_target_client_slug(client_slug)
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

    legal_mode = prechat_legal_mode_for_config(config)

    def build_link_kwargs(current_lead: ChatbotLead) -> dict:
        link_kwargs = {
            "db": db,
            "lead": current_lead,
            "client_slug": client_slug,
            "session_id": payload.session_id,
        }
        if legal_mode == "notice_only":
            link_kwargs.update(
                {
                    "notice_version": notice_version_for_config(config),
                    "cookie_notice_opened": payload.cookie_notice_opened,
                    "privacy_notice_opened": payload.privacy_notice_opened,
                    "processing_basis": "notice_only_pending_legal_review",
                }
            )
        else:
            if payload.cookie_consent_accepted is not True or payload.privacy_consent_accepted is not True:
                raise HTTPException(status_code=422, detail="Required consent is missing.")
            link_kwargs["consent_version"] = consent_version_for_config(config)
        return link_kwargs

    conversation_session_id = payload.chat_session_id or payload.session_id
    link_lead_session(**build_link_kwargs(lead))
    db.flush()
    conversation = ensure_conversation(
        db=db,
        client_slug=client_slug,
        session_id=conversation_session_id,
        lead_session_id=payload.session_id,
        config=config,
        language="en",
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
        link_lead_session(**build_link_kwargs(lead))
        db.flush()
        conversation = ensure_conversation(
            db=db,
            client_slug=client_slug,
            session_id=conversation_session_id,
            lead_session_id=payload.session_id,
            config=config,
            language="en",
        )
        created = False
        db.commit()

    db.refresh(lead)
    db.refresh(conversation)
    return {
        "success": True,
        "created": created,
        "client_slug": lead.client_slug,
        "session_id": payload.session_id,
        "chat_session_id": conversation_session_id,
        "lead_id": str(lead.id),
        "conversation_id": str(conversation.id),
    }


def callback_response_message(*, already_pending: bool, language: str) -> str:
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
    enforce_target_client_slug(client_slug)

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
    already_pending = existing_pending is not None

    if existing_pending is None:
        callback_request = SalesCallbackRequest(
            client_slug=client_slug,
            lead_id=lead.id,
            session_id=payload.session_id,
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


def stream_error_from_line(line: str) -> str:
    try:
        event = json.loads(line)
    except Exception:
        return ""

    if event.get("type") != "error":
        return ""

    return str(event.get("message") or "").strip()


def stream_done_error_state_from_line(line: str) -> str:
    try:
        event = json.loads(line)
    except Exception:
        return ""

    if event.get("type") != "done":
        return ""

    error_state = event.get("error_state")
    return error_state.strip()[:80] if isinstance(error_state, str) else ""


def product_references_from_stream_line(line: str) -> list[dict] | None:
    try:
        event = json.loads(line)
    except Exception:
        return None
    references = event.get("product_references")
    if isinstance(references, list):
        return [reference for reference in references if isinstance(reference, dict)]
    return None


def encode_event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def compact_voice_answer(answer: str, *, max_characters: int = 280) -> str:
    plain = re.sub(r"(?m)^\s*(?:#{1,6}\s*|[-*•]\s*)", "", answer or "")
    plain = plain.replace("**", "").replace("__", "")
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= max_characters:
        return plain

    sentences = re.split(r"(?<=[.!?؟])\s+", plain)
    first_sentence = sentences[0].strip() if sentences else ""
    if first_sentence and len(first_sentence) <= max_characters:
        return first_sentence

    boundary = max(plain.rfind("،", 0, max_characters), plain.rfind(",", 0, max_characters))
    if boundary < max_characters // 2:
        boundary = max_characters
    return plain[:boundary].rstrip(" ،,") + "…"


def voice_question_needs_full_commercial_answer(question: str) -> bool:
    return question_requests_comprehensive_answer(question)


def compact_voice_stream_line(line: str, *, question: str = "") -> str:
    try:
        event = json.loads(line)
    except Exception:
        return line
    if (
        event.get("type") == "replace"
        and isinstance(event.get("answer"), str)
        and not voice_question_needs_full_commercial_answer(question)
    ):
        event["answer"] = compact_voice_answer(event["answer"])
        return encode_event(event)
    return line


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
    "/chat/{client_slug}/transcribe",
    response_model=VoiceTranscriptionResponse,
    summary="Transcribe a gated voice message in the page language",
)
async def transcribe_client_voice(
    client_slug: str,
    audio: UploadFile = File(...),
    language: str = Form(...),
    lead_session_id: str = Form(...),
    db: Session = Depends(get_db),
):
    enforce_target_client_slug(client_slug)
    ensure_lead_capture_completed(
        db=db,
        client_slug=client_slug,
        session_id=lead_session_id,
    )

    clean_language = language.strip().lower()
    if clean_language not in {"en", "ar"}:
        raise HTTPException(status_code=422, detail="Voice language must be English or Arabic.")

    content_type = normalize_audio_content_type(audio.content_type)
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")

    maximum_bytes = settings.voice_max_upload_mb * 1024 * 1024
    try:
        audio_bytes = await audio.read(maximum_bytes + 1)
    finally:
        await audio.close()

    if not audio_bytes:
        raise HTTPException(status_code=422, detail="The audio recording is empty.")
    if len(audio_bytes) > maximum_bytes:
        raise HTTPException(status_code=413, detail="The audio recording is too large.")

    try:
        result = await run_in_threadpool(
            transcribe_soniox_audio,
            audio_bytes,
            content_type=content_type,
            language=clean_language,
        )
    except (SonioxConfigurationError, SonioxSpeechError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return VoiceTranscriptionResponse(
        transcript=result.transcript,
        confidence=result.confidence,
        language=result.requested_language,
        provider_language=result.provider_language,
    )


@router.post(
    "/chat/{client_slug}/speak",
    summary="Speak a bilingual answer through Soniox",
)
async def speak_client_answer(
    client_slug: str,
    payload: VoiceSpeechPayload,
    db: Session = Depends(get_db),
):
    enforce_target_client_slug(client_slug)
    ensure_lead_capture_completed(
        db=db,
        client_slug=client_slug,
        session_id=payload.lead_session_id,
    )
    try:
        prepare_soniox_speech(text=payload.text, language=payload.language)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    def audio_generator():
        try:
            yield from stream_soniox_speech(
                text=payload.text,
                language=payload.language,
            )
        except (SonioxConfigurationError, SonioxSpeechError) as error:
            print(f"[soniox voice generation error] {type(error).__name__}: {error}")
            return

    return StreamingResponse(
        audio_generator(),
        media_type="audio/L16;rate=24000;channels=1",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
            "X-Voice-Provider": soniox_voice_provider_name(),
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
    enforce_target_client_slug(client_slug)
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
        error_text = ""
        answer_error_state = ""
        product_references = None
        try:
            conversation = save_customer_message(
                db=db,
                client_slug=client_slug,
                session_id=payload.session_id,
                lead_session_id=payload.lead_session_id,
                config=config,
                message=payload.message,
            )
            db.commit()
            db.refresh(conversation)
        except Exception:
            db.rollback()
            print("[conversation storage error] customer message was not saved")
            yield encode_event(
                {
                    "type": "replace",
                    "answer": business_generation_fallback(payload.message),
                    "grounded": False,
                    "conversation_memory": False,
                    "disclaimer": None,
                    "sources": [],
                    "media": [],
                }
            )
            yield encode_event(
                {
                    "type": "done",
                    "grounded": False,
                    "conversation_memory": False,
                    "model_called": False,
                    "error_state": "conversation_storage_error",
                }
            )
            return

        last_product_reference, last_product_references = load_product_context(
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
            try:
                save_assistant_message(
                    db=db,
                    conversation=conversation,
                    message=history_answer,
                )
                db.commit()
            except Exception:
                db.rollback()
                print("[conversation storage error] assistant history answer was not saved")
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
                try:
                    save_assistant_message(
                        db=db,
                        conversation=conversation,
                        message=about_answer,
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    print("[conversation storage error] assistant about answer was not saved")
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
            voice_mode=payload.input_mode == "voice",
        ):
            if payload.input_mode == "voice":
                line = compact_voice_stream_line(line, question=payload.message)
            answer_text = update_streamed_answer(answer_text, line)
            error_text = stream_error_from_line(line) or error_text
            answer_error_state = stream_done_error_state_from_line(line) or answer_error_state
            streamed_references = product_references_from_stream_line(line)
            if streamed_references is not None:
                product_references = streamed_references
            yield line

        if answer_text.strip():
            append_exchange(
                client_slug=client_slug,
                session_id=payload.session_id,
                user_message=payload.message,
                assistant_message=answer_text,
                product_references=product_references,
            )
            try:
                save_assistant_message(
                    db=db,
                    conversation=conversation,
                    message=answer_text,
                    error_state=answer_error_state,
                )
                db.commit()
            except Exception:
                db.rollback()
                print("[conversation storage error] assistant streamed answer was not saved")
        elif error_text.strip():
            try:
                save_assistant_message(
                    db=db,
                    conversation=conversation,
                    message=error_text,
                    error_state="generation_error",
                )
                db.commit()
            except Exception:
                db.rollback()
                print("[conversation storage error] assistant stream error was not saved")

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
