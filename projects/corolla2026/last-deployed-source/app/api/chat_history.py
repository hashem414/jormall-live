from __future__ import annotations

import csv
import hmac
import os
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.constants import ASSET_VERSION
from app.core.database import get_db
from app.models.document import ChatConversation, ChatConversationMessage
from app.services import dashboard_auth_service
from app.services.client_config_service import load_client_config


TARGET_CLIENT_SLUG = os.getenv("STANDALONE_CLIENT_SLUG", "").strip()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(tags=["Chat History Dashboard"])


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="open", max_length=30)
    follow_up_status: str = Field(default="", max_length=40)
    assignee: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)


def target_client_slug() -> str:
    if TARGET_CLIENT_SLUG:
        return TARGET_CLIENT_SLUG
    return "-".join(["central", "e", "commerce", "co", "ltd"])


def dashboard_enabled() -> bool:
    if not getattr(dashboard_auth_service.settings, "chat_history_dashboard_enabled", True):
        return False
    try:
        config = load_client_config(target_client_slug())
    except FileNotFoundError:
        return False
    return bool(getattr(config, "include_chat_history_dashboard", True))


def ensure_enabled() -> None:
    if not dashboard_enabled():
        raise HTTPException(status_code=404, detail="Chat history dashboard is not enabled.")


def redirect_to_dashboard() -> RedirectResponse:
    return RedirectResponse(
        url=dashboard_auth_service.public_path("/chat-history/"),
        status_code=303,
    )


def dashboard_logo_url() -> str:
    try:
        config = load_client_config(target_client_slug())
    except FileNotFoundError:
        return dashboard_auth_service.public_path(
            "/static/client_assets/central-trade-auto-co-markazia-toyota-jordan/logo.jpg"
        )
    logo_url = config.logo_url or "/static/client_assets/central-trade-auto-co-markazia-toyota-jordan/logo.jpg"
    if logo_url.startswith("/"):
        return dashboard_auth_service.public_path(logo_url)
    return logo_url


def template_context(
    *,
    authenticated: bool,
    login_message: str = "",
    csrf_token: str = "",
) -> dict[str, object]:
    return {
        "asset_version": ASSET_VERSION,
        "authenticated": authenticated,
        "login_message": login_message,
        "csrf_token": csrf_token,
        "app_base_path": dashboard_auth_service.clean_base_path(),
        "dashboard_base_path": dashboard_auth_service.clean_base_path(),
        "next_path": dashboard_auth_service.public_path("/chat-history/"),
        "logo_url": dashboard_logo_url(),
    }


def render_login(request: Request, *, message: str = "", status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="chat_history.html",
        status_code=status_code,
        context=template_context(authenticated=False, login_message=message),
    )


def conversation_filters(
    *,
    status: str = "all",
    search: str = "",
    date_range: str = "all",
    archived: str = "active",
) -> dict[str, str]:
    return {
        "status": status if status in {"open", "pending", "resolved", "all"} else "all",
        "search": search.strip()[:100],
        "date_range": date_range if date_range in {"today", "7d", "all"} else "all",
        "archived": archived if archived in {"active", "archived", "all"} else "active",
    }


def conversation_statement(*, status: str, search: str, date_range: str, archived: str):
    filters = conversation_filters(
        status=status,
        search=search,
        date_range=date_range,
        archived=archived,
    )
    statement = (
        select(ChatConversation)
        .where(ChatConversation.client_slug == target_client_slug())
        .order_by(
            case((ChatConversation.status == "open", 0), else_=1),
            ChatConversation.last_message_at.desc(),
        )
    )

    if filters["status"] != "all":
        statement = statement.where(ChatConversation.status == filters["status"])
    if filters["archived"] == "active":
        statement = statement.where(ChatConversation.archived.is_(False))
    elif filters["archived"] == "archived":
        statement = statement.where(ChatConversation.archived.is_(True))
    if filters["search"]:
        like_pattern = f"%{filters['search']}%"
        statement = statement.where(
            or_(
                ChatConversation.customer_name.ilike(like_pattern),
                ChatConversation.customer_phone.ilike(like_pattern),
                ChatConversation.customer_company.ilike(like_pattern),
                ChatConversation.session_id.ilike(like_pattern),
                ChatConversation.assignee.ilike(like_pattern),
            )
        )

    now = datetime.now(UTC)
    if filters["date_range"] == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        statement = statement.where(ChatConversation.last_message_at >= start)
    elif filters["date_range"] == "7d":
        statement = statement.where(ChatConversation.last_message_at >= now - timedelta(days=7))
    return statement


def format_conversation(conversation: ChatConversation) -> dict[str, object]:
    return {
        "id": str(conversation.id),
        "client_slug": conversation.client_slug,
        "session_id": conversation.session_id,
        "lead_session_id": conversation.lead_session_id or "",
        "customer_name": conversation.customer_name,
        "customer_phone": conversation.customer_phone,
        "customer_company": conversation.customer_company,
        "status": conversation.status,
        "follow_up_status": conversation.follow_up_status,
        "assignee": conversation.assignee,
        "notes": conversation.notes,
        "archived": conversation.archived,
        "last_message_at": conversation.last_message_at.isoformat(),
        "last_message_date": conversation.last_message_at.strftime("%Y-%m-%d"),
        "last_message_time": conversation.last_message_at.strftime("%H:%M"),
        "message_count": len(getattr(conversation, "messages", []) or []),
    }


def format_message(message: ChatConversationMessage) -> dict[str, object]:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "language": message.language,
        "media": message.media or [],
        "created_at": message.created_at.isoformat(),
    }


@router.get("/chat-history", include_in_schema=False)
def legacy_chat_history_redirect():
    ensure_enabled()
    return redirect_to_dashboard()


@router.get("/chat-history/", response_class=HTMLResponse, include_in_schema=False)
def chat_history_dashboard(request: Request):
    ensure_enabled()
    session = dashboard_auth_service.read_session_cookie(request)
    if session is None:
        return dashboard_auth_service.redirect_to_login(
            dashboard_auth_service.public_path("/chat-history/")
        )
    return templates.TemplateResponse(
        request=request,
        name="chat_history.html",
        context=template_context(authenticated=True, csrf_token=str(session["csrf"])),
    )


@router.get("/api/admin/chat-history/conversations")
def dashboard_conversations(
    request: Request,
    status: str = "all",
    search: str = "",
    date_range: str = "all",
    archived: str = "active",
    _: dict[str, object] = Depends(dashboard_auth_service.require_dashboard_session),
    db: Session = Depends(get_db),
):
    ensure_enabled()
    rows = list(
        db.execute(
            conversation_statement(
                status=status,
                search=search,
                date_range=date_range,
                archived=archived,
            ).options(selectinload(ChatConversation.messages))
        ).scalars()
    )
    return {
        "client_slug": target_client_slug(),
        "total": len(rows),
        "conversations": [format_conversation(row) for row in rows],
    }


@router.get("/api/admin/chat-history/conversations/{conversation_id}")
def dashboard_conversation_detail(
    conversation_id: UUID,
    request: Request,
    _: dict[str, object] = Depends(dashboard_auth_service.require_dashboard_session),
    db: Session = Depends(get_db),
):
    ensure_enabled()
    conversation = db.scalar(
        select(ChatConversation)
        .options(selectinload(ChatConversation.messages))
        .where(
            ChatConversation.id == conversation_id,
            ChatConversation.client_slug == target_client_slug(),
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        "conversation": format_conversation(conversation),
        "messages": [
            format_message(message)
            for message in sorted(conversation.messages, key=lambda item: item.created_at)
        ],
    }


@router.post("/api/admin/chat-history/conversations/{conversation_id}/update")
def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    request: Request,
    session: dict[str, object] = Depends(dashboard_auth_service.require_dashboard_session),
    db: Session = Depends(get_db),
):
    ensure_enabled()
    dashboard_auth_service.require_csrf(request, session)
    conversation = db.scalar(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.client_slug == target_client_slug(),
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    conversation.status = payload.status if payload.status in {"open", "pending", "resolved"} else "open"
    conversation.follow_up_status = payload.follow_up_status.strip()
    conversation.assignee = payload.assignee.strip()
    conversation.notes = payload.notes.strip()
    conversation.updated_at = func.now()
    db.commit()
    return {"success": True, "conversation": format_conversation(conversation)}


@router.post("/api/admin/chat-history/conversations/{conversation_id}/archive")
def archive_conversation(
    conversation_id: UUID,
    request: Request,
    session: dict[str, object] = Depends(dashboard_auth_service.require_dashboard_session),
    db: Session = Depends(get_db),
):
    ensure_enabled()
    dashboard_auth_service.require_csrf(request, session)
    conversation = db.scalar(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.client_slug == target_client_slug(),
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    conversation.archived = True
    conversation.updated_at = func.now()
    db.commit()
    return {"success": True}


@router.post("/api/admin/chat-history/conversations/{conversation_id}/restore")
def restore_conversation(
    conversation_id: UUID,
    request: Request,
    session: dict[str, object] = Depends(dashboard_auth_service.require_dashboard_session),
    db: Session = Depends(get_db),
):
    ensure_enabled()
    dashboard_auth_service.require_csrf(request, session)
    conversation = db.scalar(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.client_slug == target_client_slug(),
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    conversation.archived = False
    conversation.updated_at = func.now()
    db.commit()
    return {"success": True}


@router.get("/api/admin/chat-history/export.csv")
def dashboard_chat_history_export(
    request: Request,
    status: str = "all",
    search: str = "",
    date_range: str = "all",
    archived: str = "active",
    _: dict[str, object] = Depends(dashboard_auth_service.require_dashboard_session),
    db: Session = Depends(get_db),
):
    ensure_enabled()
    rows = list(
        db.execute(
            conversation_statement(
                status=status,
                search=search,
                date_range=date_range,
                archived=archived,
            )
        ).scalars()
    )
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Customer Name",
            "Mobile Number",
            "Session ID",
            "Status",
            "Follow Up",
            "Assignee",
            "Last Message At",
            "Archived",
            "Notes",
        ]
    )
    for conversation in rows:
        writer.writerow(
            [
                conversation.customer_name,
                conversation.customer_phone,
                conversation.session_id,
                conversation.status,
                conversation.follow_up_status,
                conversation.assignee,
                conversation.last_message_at.isoformat(),
                "yes" if conversation.archived else "no",
                conversation.notes,
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=chat_history.csv"},
    )
