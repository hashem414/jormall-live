from __future__ import annotations

import csv
import hmac
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.sales_callbacks import (
    SESSION_COOKIE_NAME,
    clear_failed_logins,
    cookie_path,
    create_session_cookie,
    dashboard_password,
    is_https_request,
    login_blocked,
    read_session_cookie,
    remember_failed_login,
    require_csrf,
    require_dashboard_session,
    request_base_path,
)
from app.constants import ASSET_VERSION
from app.core.config import settings
from app.core.database import get_db
from app.models.document import ChatConversation, ChatConversationMessage
from app.services.conversation_store import (
    MAX_ASSIGNMENT_CHARACTERS,
    MAX_NOTE_CHARACTERS,
    VALID_CONVERSATION_STATUSES,
    clean_text,
)


TARGET_CLIENT_SLUG = "central-e-commerce-co-ltd"
MAX_PAGE_SIZE = 100
BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["Chat History Dashboard"])


class ConversationStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        clean = value.strip()
        if clean not in VALID_CONVERSATION_STATUSES:
            raise ValueError("Unsupported conversation status.")
        return clean


class ConversationAssignmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_employee: str = Field(default="", max_length=MAX_ASSIGNMENT_CHARACTERS)

    @field_validator("assigned_employee")
    @classmethod
    def clean_assigned_employee(cls, value: str) -> str:
        return clean_text(value, limit=MAX_ASSIGNMENT_CHARACTERS)


class ConversationFollowUpPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    follow_up_required: bool


class ConversationNotesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_notes: str = Field(default="", max_length=MAX_NOTE_CHARACTERS)

    @field_validator("internal_notes")
    @classmethod
    def clean_internal_notes(cls, value: str) -> str:
        return (value or "").strip()[:MAX_NOTE_CHARACTERS]


class ConversationFilterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = 1
    page_size: int = 25
    search: str = ""
    campaign: str = ""
    client: str = ""
    status: str = "active"
    assigned_employee: str = ""
    language: str = ""
    follow_up: str = "all"
    date_from: str = ""
    date_to: str = ""


def feature_enabled() -> None:
    if not settings.chat_history_enabled:
        raise HTTPException(status_code=404, detail="Chat history is not enabled.")


def chat_history_path(request: Request) -> str:
    return f"{request_base_path(request)}/chat-history/"


def redirect_to_chat_history(request: Request) -> RedirectResponse:
    return RedirectResponse(url=chat_history_path(request), status_code=303)


def render_chat_history_login(
    request: Request,
    *,
    message: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="chat_history.html",
        status_code=status_code,
        context={
            "asset_version": ASSET_VERSION,
            "authenticated": False,
            "login_message": message,
            "csrf_token": "",
            "app_base_path": request_base_path(request),
            "dashboard_path": chat_history_path(request),
        },
    )


def local_time(value: datetime | None) -> tuple[str, str, str]:
    if value is None:
        return "", "", ""
    try:
        zone = ZoneInfo(settings.app_timezone)
    except Exception:
        zone = ZoneInfo("Asia/Amman")
    converted = value
    if converted.tzinfo is None:
        converted = converted.replace(tzinfo=UTC)
    converted = converted.astimezone(zone)
    return converted.isoformat(), converted.strftime("%Y-%m-%d"), converted.strftime("%H:%M")


def mask_mobile(phone: str) -> str:
    clean = (phone or "").strip()
    if len(clean) < 7:
        return clean
    return f"{clean[:3]}****{clean[-3:]}"


def parse_date(value: str) -> datetime | None:
    clean = (value or "").strip()[:10]
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean).replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date filter.")


def filtered_conversation_statement(
    *,
    search: str = "",
    campaign: str = "",
    client: str = "",
    status: str = "active",
    assigned_employee: str = "",
    language: str = "",
    follow_up: str = "",
    date_from: str = "",
    date_to: str = "",
):
    statement = select(ChatConversation).where(
        ChatConversation.client_slug == TARGET_CLIENT_SLUG
    )

    if status == "active":
        statement = statement.where(ChatConversation.status != "archived")
    elif status in VALID_CONVERSATION_STATUSES:
        statement = statement.where(ChatConversation.status == status)
    elif status and status != "all":
        raise HTTPException(status_code=422, detail="Invalid status filter.")

    clean_search = clean_text(search, limit=100)
    if clean_search:
        pattern = f"%{clean_search}%"
        statement = statement.where(
            or_(
                ChatConversation.customer_name.ilike(pattern),
                ChatConversation.customer_mobile.ilike(pattern),
                ChatConversation.public_session_id.ilike(pattern),
                cast(ChatConversation.id, String).ilike(pattern),
            )
        )

    clean_campaign = clean_text(campaign, limit=100)
    if clean_campaign:
        statement = statement.where(ChatConversation.campaign_name.ilike(f"%{clean_campaign}%"))

    clean_client = clean_text(client, limit=100)
    if clean_client:
        statement = statement.where(ChatConversation.client_slug == clean_client)

    clean_assigned = clean_text(assigned_employee, limit=MAX_ASSIGNMENT_CHARACTERS)
    if clean_assigned:
        statement = statement.where(ChatConversation.assigned_employee.ilike(f"%{clean_assigned}%"))

    clean_language = clean_text(language, limit=10)
    if clean_language:
        statement = statement.where(ChatConversation.language == clean_language)

    if follow_up in {"true", "false"}:
        statement = statement.where(ChatConversation.follow_up_required.is_(follow_up == "true"))
    elif follow_up and follow_up != "all":
        raise HTTPException(status_code=422, detail="Invalid follow-up filter.")

    start = parse_date(date_from)
    if start:
        statement = statement.where(ChatConversation.started_at >= start)
    end = parse_date(date_to)
    if end:
        statement = statement.where(ChatConversation.started_at < end + timedelta(days=1))

    return statement


def message_count_subquery():
    return (
        select(
            ChatConversationMessage.conversation_id,
            func.count(ChatConversationMessage.id).label("message_count"),
        )
        .group_by(ChatConversationMessage.conversation_id)
        .subquery()
    )


def format_conversation_row(
    conversation: ChatConversation,
    *,
    message_count: int = 0,
    reveal_phone: bool = False,
) -> dict[str, object]:
    started_iso, started_date, started_time = local_time(conversation.started_at)
    last_iso, last_date, last_time = local_time(conversation.last_activity_at)
    completed_iso, _, _ = local_time(conversation.completed_at)
    return {
        "id": str(conversation.id),
        "conversation_id": str(conversation.id),
        "session_id": conversation.public_session_id,
        "client_slug": conversation.client_slug,
        "campaign_name": conversation.campaign_name,
        "chatbot_name": conversation.chatbot_name,
        "customer_name": conversation.customer_name,
        "customer_mobile": conversation.customer_mobile if reveal_phone else mask_mobile(conversation.customer_mobile),
        "language": conversation.language,
        "source": conversation.source,
        "status": conversation.status,
        "assigned_employee": conversation.assigned_employee,
        "follow_up_required": conversation.follow_up_required,
        "internal_notes": conversation.internal_notes if reveal_phone else "",
        "started_at": started_iso,
        "started_date": started_date,
        "started_time": started_time,
        "last_activity_at": last_iso,
        "last_activity_date": last_date,
        "last_activity_time": last_time,
        "completed_at": completed_iso,
        "message_count": int(message_count or 0),
    }


def get_conversation_or_404(db: Session, conversation_id: UUID) -> ChatConversation:
    conversation = db.scalar(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.client_slug == TARGET_CLIENT_SLUG,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


def safe_csv_value(value: object) -> str:
    text = str(value or "")
    if text and text[0] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def commit_and_refresh(db: Session, conversation: ChatConversation) -> None:
    db.commit()
    db.refresh(conversation)


def conversation_list_response(
    *,
    db: Session,
    page: int = 1,
    page_size: int = 25,
    search: str = "",
    campaign: str = "",
    client: str = "",
    status: str = "active",
    assigned_employee: str = "",
    language: str = "",
    follow_up: str = "all",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, object]:
    clean_page = max(page, 1)
    clean_page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    base = filtered_conversation_statement(
        search=search,
        campaign=campaign,
        client=client,
        status=status,
        assigned_employee=assigned_employee,
        language=language,
        follow_up=follow_up,
        date_from=date_from,
        date_to=date_to,
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    counts = message_count_subquery()
    rows = db.execute(
        base.add_columns(func.coalesce(counts.c.message_count, 0))
        .outerjoin(counts, counts.c.conversation_id == ChatConversation.id)
        .order_by(ChatConversation.last_activity_at.desc(), ChatConversation.started_at.desc())
        .offset((clean_page - 1) * clean_page_size)
        .limit(clean_page_size)
    ).all()

    return {
        "client_slug": TARGET_CLIENT_SLUG,
        "page": clean_page,
        "page_size": clean_page_size,
        "total": int(total),
        "can_reveal_phone": True,
        "conversations": [
            format_conversation_row(conversation, message_count=message_count)
            for conversation, message_count in rows
        ],
    }


def export_conversations_response(
    *,
    db: Session,
    search: str = "",
    campaign: str = "",
    client: str = "",
    status: str = "active",
    assigned_employee: str = "",
    language: str = "",
    follow_up: str = "all",
    date_from: str = "",
    date_to: str = "",
) -> Response:
    base = filtered_conversation_statement(
        search=search,
        campaign=campaign,
        client=client,
        status=status,
        assigned_employee=assigned_employee,
        language=language,
        follow_up=follow_up,
        date_from=date_from,
        date_to=date_to,
    )
    counts = message_count_subquery()
    rows = db.execute(
        base.add_columns(func.coalesce(counts.c.message_count, 0))
        .outerjoin(counts, counts.c.conversation_id == ChatConversation.id)
        .order_by(ChatConversation.last_activity_at.desc())
        .limit(settings.chat_export_max_rows)
    ).all()

    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Conversation ID",
            "Session ID",
            "Customer Name",
            "Mobile Number",
            "Campaign",
            "Chatbot/Client",
            "Language",
            "Status",
            "Assigned Employee",
            "Follow-up Required",
            "Started At",
            "Last Activity At",
            "Message Count",
            "Internal Notes",
        ]
    )
    for conversation, message_count in rows:
        row = format_conversation_row(
            conversation,
            message_count=message_count,
            reveal_phone=True,
        )
        writer.writerow(
            [
                safe_csv_value(row["conversation_id"]),
                safe_csv_value(row["session_id"]),
                safe_csv_value(row["customer_name"]),
                safe_csv_value(row["customer_mobile"]),
                safe_csv_value(row["campaign_name"]),
                safe_csv_value(row["chatbot_name"]),
                safe_csv_value(row["language"]),
                safe_csv_value(row["status"]),
                safe_csv_value(row["assigned_employee"]),
                safe_csv_value("yes" if row["follow_up_required"] else "no"),
                safe_csv_value(row["started_at"]),
                safe_csv_value(row["last_activity_at"]),
                safe_csv_value(row["message_count"]),
                safe_csv_value(conversation.internal_notes),
            ]
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=chat_conversations.csv"},
    )


@router.get("/chat-history", include_in_schema=False)
def chat_history_slash_redirect(request: Request):
    feature_enabled()
    return redirect_to_chat_history(request)


@router.get("/chat-history/", response_class=HTMLResponse, include_in_schema=False)
def chat_history_dashboard(request: Request):
    feature_enabled()
    session = read_session_cookie(request)
    if session is None:
        return render_chat_history_login(request)

    return templates.TemplateResponse(
        request=request,
        name="chat_history.html",
        context={
            "asset_version": ASSET_VERSION,
            "authenticated": True,
            "login_message": "",
            "csrf_token": session["csrf"],
            "app_base_path": request_base_path(request),
            "dashboard_path": chat_history_path(request),
        },
    )


@router.post("/chat-history/login", include_in_schema=False)
def chat_history_login(request: Request, password: str = Form("")):
    feature_enabled()
    configured_password = dashboard_password()
    if not configured_password:
        return render_chat_history_login(
            request,
            message="Dashboard password is not configured.",
            status_code=503,
        )

    if login_blocked(request):
        return render_chat_history_login(
            request,
            message="Too many failed attempts. Please try again later.",
            status_code=429,
        )

    if not hmac.compare_digest(password, configured_password):
        remember_failed_login(request)
        return render_chat_history_login(
            request,
            message="Access denied. Please check the password.",
            status_code=401,
        )

    clear_failed_logins(request)
    cookie_value, _ = create_session_cookie()
    response = redirect_to_chat_history(request)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=settings.admin_session_timeout,
        httponly=True,
        secure=is_https_request(request),
        samesite="lax",
        path=cookie_path(request),
    )
    return response


@router.post("/chat-history/logout", include_in_schema=False)
def chat_history_logout(request: Request):
    response = redirect_to_chat_history(request)
    response.delete_cookie(SESSION_COOKIE_NAME, path=cookie_path(request))
    return response


@router.get("/api/admin/conversations")
def list_conversations(
    request: Request,
    page: int = 1,
    page_size: int = 25,
    search: str = "",
    campaign: str = "",
    client: str = "",
    status: str = "active",
    assigned_employee: str = "",
    language: str = "",
    follow_up: str = "all",
    date_from: str = "",
    date_to: str = "",
    _: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    return conversation_list_response(
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        campaign=campaign,
        client=client,
        status=status,
        assigned_employee=assigned_employee,
        language=language,
        follow_up=follow_up,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/api/admin/conversations/search")
def search_conversations(
    payload: ConversationFilterPayload,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    return conversation_list_response(db=db, **payload.model_dump())


@router.get("/api/admin/conversations/export.csv")
def export_conversations(
    request: Request,
    search: str = "",
    campaign: str = "",
    client: str = "",
    status: str = "active",
    assigned_employee: str = "",
    language: str = "",
    follow_up: str = "all",
    date_from: str = "",
    date_to: str = "",
    _: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    return export_conversations_response(
        db=db,
        search=search,
        campaign=campaign,
        client=client,
        status=status,
        assigned_employee=assigned_employee,
        language=language,
        follow_up=follow_up,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/api/admin/conversations/export.csv")
def export_conversations_from_body(
    payload: ConversationFilterPayload,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    values = payload.model_dump()
    values.pop("page", None)
    values.pop("page_size", None)
    return export_conversations_response(db=db, **values)


@router.get("/api/admin/conversations/{conversation_id}")
def get_conversation_detail(
    conversation_id: UUID,
    request: Request,
    _: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    conversation = get_conversation_or_404(db, conversation_id)
    messages = db.scalars(
        select(ChatConversationMessage)
        .where(ChatConversationMessage.conversation_id == conversation.id)
        .order_by(ChatConversationMessage.created_at.asc())
    ).all()
    return {
        "conversation": format_conversation_row(
            conversation,
            message_count=len(messages),
            reveal_phone=True,
        ),
        "messages": [
            {
                "id": str(message.id),
                "role": message.role,
                "content": message.content,
                "created_at": local_time(message.created_at)[0],
                "created_date": local_time(message.created_at)[1],
                "created_time": local_time(message.created_at)[2],
                "error_state": message.error_state,
            }
            for message in messages
        ],
    }


@router.patch("/api/admin/conversations/{conversation_id}/status")
def update_conversation_status(
    conversation_id: UUID,
    payload: ConversationStatusPayload,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    conversation = get_conversation_or_404(db, conversation_id)
    conversation.status = payload.status
    conversation.completed_at = func.now() if payload.status == "completed" else None
    conversation.updated_at = func.now()
    commit_and_refresh(db, conversation)
    return {"success": True, "conversation": format_conversation_row(conversation, reveal_phone=True)}


@router.patch("/api/admin/conversations/{conversation_id}/assignment")
def update_conversation_assignment(
    conversation_id: UUID,
    payload: ConversationAssignmentPayload,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    conversation = get_conversation_or_404(db, conversation_id)
    conversation.assigned_employee = payload.assigned_employee
    if payload.assigned_employee and conversation.status == "open":
        conversation.status = "assigned"
    conversation.updated_at = func.now()
    commit_and_refresh(db, conversation)
    return {"success": True, "conversation": format_conversation_row(conversation, reveal_phone=True)}


@router.patch("/api/admin/conversations/{conversation_id}/follow-up")
def update_conversation_follow_up(
    conversation_id: UUID,
    payload: ConversationFollowUpPayload,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    conversation = get_conversation_or_404(db, conversation_id)
    conversation.follow_up_required = payload.follow_up_required
    if payload.follow_up_required and conversation.status == "open":
        conversation.status = "needs_follow_up"
    conversation.updated_at = func.now()
    commit_and_refresh(db, conversation)
    return {"success": True, "conversation": format_conversation_row(conversation, reveal_phone=True)}


@router.patch("/api/admin/conversations/{conversation_id}/notes")
def update_conversation_notes(
    conversation_id: UUID,
    payload: ConversationNotesPayload,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    conversation = get_conversation_or_404(db, conversation_id)
    conversation.internal_notes = payload.internal_notes
    conversation.updated_at = func.now()
    commit_and_refresh(db, conversation)
    return {"success": True, "conversation": format_conversation_row(conversation, reveal_phone=True)}


@router.post("/api/admin/conversations/{conversation_id}/archive")
def archive_conversation(
    conversation_id: UUID,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    conversation = get_conversation_or_404(db, conversation_id)
    conversation.status = "archived"
    conversation.updated_at = func.now()
    commit_and_refresh(db, conversation)
    return {"success": True, "conversation": format_conversation_row(conversation, reveal_phone=True)}


@router.post("/api/admin/conversations/{conversation_id}/restore")
def restore_conversation(
    conversation_id: UUID,
    request: Request,
    session: dict[str, object] = Depends(require_dashboard_session),
    db: Session = Depends(get_db),
):
    feature_enabled()
    require_csrf(request, session)
    conversation = get_conversation_or_404(db, conversation_id)
    if conversation.status == "archived":
        conversation.status = "open"
    conversation.updated_at = func.now()
    commit_and_refresh(db, conversation)
    return {"success": True, "conversation": format_conversation_row(conversation, reveal_phone=True)}
