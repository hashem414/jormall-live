from flask import Flask, Response, request, jsonify, send_from_directory, session, abort, send_file
from flask_session import Session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=False)

import uuid
import numpy as np
import fitz  # PyMuPDF for PDF text extraction
from docx import Document
import requests
import docx
import json
import re
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from functools import wraps
from uuid import uuid4
import tempfile
import traceback
from io import BytesIO
from urllib.parse import quote
from modules.sms_bitly_dashboard_routes import bp as sms_bitly_bp
from modules.generate_ai_docx_with_markdown import generate_ai_docx
from modules.generate_ai_docx_with_markdown_arabic import generate_ai_docx as generate_arabic_ai_docx
from modules.smart_sms_campaign_generation import run_smart_sms_campaign_generation
from modules.chain_sms_campaign_generation import run_chain_sms_campaign_generation
from modules.premium_sms_campaign_generation import run_premium_sms_campaign_generation
from modules.personalized_sms_campaign_generation import run_personalized_sms_campaign_generation
from modules.lead_sms_campaign_generation import run_lead_sms_campaign_generation
from modules.optin_sms_campaign_generation import run_optin_sms_campaign_generation
from modules.profile_analysis_generation import run_profile_analysis_generation
from modules.marketing_plan_generation import  run_marketing_plan_generation
from modules.platform_benefits_generation import (
    run_platform_benefits_generation,
    SUPPORTED_INDUSTRIES as PLATFORM_BENEFITS_INDUSTRIES,
)
from modules.ai_products_generation import run_ai_product_generation, PRODUCTS as AI_PRODUCTS
from modules.translate_campaign_json_to_arabic import translate_campaign_json_to_arabic
from modules.website_crawler_scrapper import fetch_website_text
from modules.openai_client import create_openai_client


# ---- Config from .env or environment ----
STATIC_FOLDER = os.path.join(BASE_DIR, "static")

def public_path(path):
    """Return a root-based browser URL for this application."""
    return "/" + str(path or "").lstrip("/")
DEFAULT_SENDER_EMAIL = os.getenv("SMTP_SENDER", "noreply@jormall.com")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.yourmailhost.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = DEFAULT_SENDER_EMAIL
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
BITLY_TOKEN = os.getenv("BITLY_API_KEY")
USER_DIRECTORY_URL = (
    os.getenv("USER_DIRECTORY_URL", "http://172.17.0.1:18101")
    .strip()
    .strip('"')
    .strip("'")
    .rstrip("/")
)
USER_DIRECTORY_TOKEN_FILE = os.getenv("USER_DIRECTORY_TOKEN_FILE", "/app/.user-directory-token")
LOG_PATH = 'logs/leads.json'
os.makedirs('logs', exist_ok=True)
DOCUMENTS_FOLDER = os.path.join(BASE_DIR, "documents")
DOCX_TABLE_KNOWLEDGE_FILES = frozenset({
    "JorMall Interactive Campaign Chatbot Hosting Packages.docx",
    "JorMall Interactive Campaign Chatbot.docx",
    "JorMall Chatbot Organization AI Assistant Hosting Packages.docx",
    "JorMall Organization AI Assistant.docx",
})
EXPORT_DIR = os.path.join(BASE_DIR, "exports", "docx")
JSON_DIR = os.path.join(BASE_DIR, "exports", "json")
BITLY_LOG_DIR = os.path.join(BASE_DIR, "exports", "bitly_logs")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
IMAGES_DIR = os.path.join(BASE_DIR, "assets", "images")
VIDEOS_DIR = os.path.join(BASE_DIR, "assets", "videos")
PRST_DIR= os.path.join(BASE_DIR, "assets", "presentations")
SMADOC_DIR= os.path.join(BASE_DIR, "assets", "SMA_documents")
FONTS_DIR = os.path.join(BASE_DIR, "assets", "fonts")
os.makedirs(EXPORT_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(BITLY_LOG_DIR, exist_ok=True)

# ---- Per-chat JSON storage and attachment settings ----
CHAT_LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(CHAT_LOGS_DIR, exist_ok=True)
MAX_ATTACHMENT_TEXT_CHARS = int(os.getenv("MAX_ATTACHMENT_TEXT_CHARS", "60000"))
MAX_CHAT_ATTACHMENT_CONTEXT_CHARS = int(os.getenv("MAX_CHAT_ATTACHMENT_CONTEXT_CHARS", "120000"))
MAX_CHAT_HISTORY_MESSAGES = int(os.getenv("MAX_CHAT_HISTORY_MESSAGES", "30"))

# ---- RAG / Embedding Analysis settings ----
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "20"))
RAG_SIMILARITY_FUNCTION = "cosine"
RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-large")
RAG_PROJECTION_METHOD = "PCA 2D"

# ---- Document Loaders ----
def extract_text_from_pdf(pdf_path):
    try:
        with open(pdf_path, 'rb') as f:
            if f.read(4) != b'%PDF':
                raise ValueError("Not a valid PDF file")
        doc = fitz.open(pdf_path)
        print("Scanning and retrieving", pdf_path)
        return "\n".join(page.get_text() for page in doc)
    except Exception as e:
        print(f"[ERROR] Skipping PDF: {pdf_path} — {e}")
        return ""

def extract_text_from_docx(docx_path):
    try:
        doc = Document(docx_path)
        print("Scanning and retrieving", docx_path)
        sections = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
        if os.path.basename(docx_path) in DOCX_TABLE_KNOWLEDGE_FILES:
            table_sections = []
            for table in doc.tables:
                rows = []
                for row in table.rows:
                    cells = [" ".join(cell.text.split()) for cell in row.cells if cell.text.strip()]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    document_name = os.path.splitext(os.path.basename(docx_path))[0]
                    table_sections.append(f"{document_name} table: " + " ; ".join(rows))
            sections = table_sections + sections
        return "\n".join(sections)
    except Exception as e:
        print(f"[ERROR] Skipping DOCX: {docx_path} — {e}")
        return ""

def load_all_documents(folder_path):
    """Backward-compatible text-only loader."""
    return [item["text"] for item in load_all_documents_with_sources(folder_path)]

def load_all_documents_with_sources(folder_path):
    """Load supported knowledge-base documents with source metadata for AI analysis."""
    records = []
    if not os.path.exists(folder_path):
        print(f"Documents folder '{folder_path}' does not exist.")
        return records

    for filename in sorted(os.listdir(folder_path)):
        full_path = os.path.join(folder_path, filename)
        if not os.path.isfile(full_path):
            continue

        lower = filename.lower()
        text = ""
        doc_type = ""
        if lower.endswith(".pdf"):
            doc_type = "pdf"
            text = extract_text_from_pdf(full_path)
        elif lower.endswith(".docx"):
            doc_type = "docx"
            text = extract_text_from_docx(full_path)

        if text:
            records.append({
                "source": filename,
                "path": full_path,
                "type": doc_type,
                "text": text,
                "word_count": len(text.split())
            })
    return records

def chunk_text(text, max_words=200):
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = []
    total_words = 0
    for para in paragraphs:
        words = para.split()
        if total_words + len(words) > max_words:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                total_words = 0
        current_chunk.extend(words)
        total_words += len(words)
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

# AI Analytics is restricted to administrative accounts and the two approved analytics users.
AI_ANALYTICS_USERS = {"admin", "ADMIN", "user30", "user31"}

# ---- OpenAI Embedding Helper ----
_openai_client = None

def get_openai_client():
    """
    Create/reuse the OpenAI client only when it is needed.
    This prevents startup/import issues and fixes: name 'get_openai_client' is not defined.
    """
    global _openai_client
    if _openai_client is None:
        api_key = (os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY or "").strip().strip('"').strip("'")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing. Add it to the .env file beside app.py.")
        _openai_client = create_openai_client(api_key)
    return _openai_client

def embed_text(text):
    response = get_openai_client().embeddings.create(
        input=[text],
        model=RAG_EMBEDDING_MODEL
    )
    return np.array(response.data[0].embedding, dtype=float)

def embed_chunks(chunks):
    """Backward-compatible embedding helper for plain text chunks."""
    records = [
        {
            "id": f"chunk_{idx}",
            "chunk": chunk,
            "source": "Knowledge base",
            "chunk_index": idx,
            "word_count": len(str(chunk).split())
        }
        for idx, chunk in enumerate(chunks, start=1)
    ]
    return embed_chunk_records(records)

def embed_chunk_records(records):
    """Embed chunks while preserving metadata for retrieval and visualization."""
    print(f"Embedding {len(records)} text chunks ...")
    if not OPENAI_API_KEY:
        print("Skipping startup embeddings because OPENAI_API_KEY is not configured.")
        return []

    embedded = []
    batch_size = max(1, min(int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "64")), 256))
    for batch_start in range(0, len(records), batch_size):
        batch = records[batch_start:batch_start + batch_size]
        try:
            valid = [(record, str(record.get("chunk") or "")) for record in batch]
            valid = [(record, chunk) for record, chunk in valid if chunk.strip()]
            if not valid:
                continue
            response = get_openai_client().embeddings.create(
                input=[chunk for _record, chunk in valid],
                model=RAG_EMBEDDING_MODEL,
            )
            vectors = {item.index: item.embedding for item in response.data}
            for offset, (record, chunk) in enumerate(valid):
                embedding = vectors.get(offset)
                if embedding is None:
                    continue
                idx = batch_start + offset + 1
                enriched = dict(record)
                enriched.setdefault("id", f"chunk_{idx}")
                enriched.setdefault("source", "Knowledge base")
                enriched.setdefault("chunk_index", idx)
                enriched.setdefault("word_count", len(chunk.split()))
                enriched["chunk"] = chunk
                enriched["embedding"] = np.array(embedding, dtype=float)
                embedded.append(enriched)
        except Exception as e:
            batch_number = batch_start // batch_size + 1
            print(f"[ERROR] Skipping embedding batch {batch_number}: {e}")
    print(f"Embedded {len(embedded)} chunks.")
    return embedded

def cosine_similarity(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

def _embedded_record(item, index=0):
    """Normalize current and older embedding tuple formats into one dict shape."""
    if isinstance(item, dict):
        record = dict(item)
    elif isinstance(item, (list, tuple)) and len(item) >= 2:
        record = {
            "id": f"legacy_chunk_{index + 1}",
            "chunk": item[0],
            "embedding": item[1],
            "source": "Knowledge base",
            "chunk_index": index + 1,
            "word_count": len(str(item[0]).split())
        }
    else:
        return None

    record.setdefault("id", f"chunk_{index + 1}")
    record.setdefault("source", "Knowledge base")
    record.setdefault("chunk_index", index + 1)
    record.setdefault("word_count", len(str(record.get("chunk") or "").split()))
    return record

def iter_embedded_records():
    for idx, item in enumerate(embedded_chunks):
        record = _embedded_record(item, idx)
        if record is not None and record.get("embedding") is not None:
            yield record

def build_knowledge_chunk_records(document_records):
    """Create chunk metadata before embedding so the UI can explain each scatter point."""
    records = []
    for doc_index, doc in enumerate(document_records, start=1):
        source = doc.get("source") or f"document_{doc_index}"
        doc_chunks = chunk_text(doc.get("text") or "")
        for chunk_index, chunk in enumerate(doc_chunks, start=1):
            records.append({
                "id": f"doc_{doc_index}_chunk_{chunk_index}",
                "chunk": chunk,
                "source": source,
                "document_index": doc_index,
                "chunk_index": chunk_index,
                "document_type": doc.get("type") or "document",
                "word_count": len(chunk.split())
            })
    return records

# --- Load & Embed Documents at Startup ---
print("Loading and embedding documents for RAG...")
document_records = load_all_documents_with_sources(DOCUMENTS_FOLDER)
knowledge_chunk_records = build_knowledge_chunk_records(document_records)
if knowledge_chunk_records:
    embedded_chunks = embed_chunk_records(knowledge_chunk_records)
else:
    print("No documents loaded; using default chunks.")
    fallback_dim = int(os.getenv("FALLBACK_EMBEDDING_DIM", "3072"))
    embedded_chunks = [
        {"id": "fallback_1", "source": "Fallback", "chunk_index": 1, "chunk": "JorMall offers SMS marketing services in Jordan.", "embedding": np.random.rand(fallback_dim), "word_count": 7},
        {"id": "fallback_2", "source": "Fallback", "chunk_index": 2, "chunk": "Bulk SMS campaigns help businesses reach a large audience.", "embedding": np.random.rand(fallback_dim), "word_count": 8},
        {"id": "fallback_3", "source": "Fallback", "chunk_index": 3, "chunk": "JorMall provides premium, interactive and service messages.", "embedding": np.random.rand(fallback_dim), "word_count": 7},
    ]

if knowledge_chunk_records and not embedded_chunks:
    print("No embeddings were created. Check OPENAI_API_KEY and network access.")

# ---- Lead Logging Helper ----


LOG_PATH = 'logs/'  # Update the path if needed


# ---- Helper: Generate Session Log Filename ----
def get_session_log_filename(name, client_name, company, start_time):
    def make_safe(s):
        return s.strip().replace(" ", "+") or "unknown"

    safe_name = make_safe(name)
    safe_client = make_safe(client_name)
    safe_company = make_safe(company)

    return f"logs/{safe_name}_{safe_client}_{safe_company}_{start_time}.json"

# ----  Helper: Admin Activity Logger ----
def _sanitize_activity_text(value, max_length=240):
    """Keep log text readable and safe without changing normal Unicode names."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = " ".join(text.split())
    return text[:max_length]

def _company_activity_description(action_label, company_name):
    company = _sanitize_activity_text(company_name, 160)
    return f"{action_label} for {company}" if company else action_label

def _campaign_activity_label(sms_type):
    labels = {
        "smart": "Create Campaign Smart",
        "chain": "Create Campaign Chain",
        "premium": "Create Campaign Premium",
        "personalized": "Create Campaign Personalized",
        "lead": "Create Campaign Lead",
        "optin": "Create Campaign Opt-In",
    }
    return labels.get(str(sms_type or "").strip().lower(), "Create SMS Document")

def log_admin_activity(username, action, description=None, **details):
    os.makedirs(LOG_PATH, exist_ok=True)
    filepath = os.path.join(LOG_PATH, "activity_log.jsonl")

    safe_details = dict(details)
    if "company_name" in safe_details:
        safe_details["company_name"] = _sanitize_activity_text(safe_details.get("company_name"), 160)
    if "error" in safe_details:
        safe_details["error"] = _sanitize_activity_text(safe_details.get("error"), 500)

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "username": _sanitize_activity_text(username, 120),
        "action": _sanitize_activity_text(action, 120),
        "description": _sanitize_activity_text(description or action, 320),
        **safe_details
    }

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
# ---- Helper: Ensure directory and write to session log file as a grouped dict ----
def log_session_entry(entry):
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)

    username = entry["name"].replace(" ", "_")
    client_name = entry["client_name"].replace(" ", "_")
    company = entry["company"].replace(" ", "_")
    timestamp = datetime.utcnow().isoformat().replace(":", "-")[:19]

    # Construct file name once per session
    if "log_file_name" not in session:
        filename = f"{username}_{client_name}_{company}_{timestamp}.json"
        session["log_file_name"] = filename
    else:
        filename = session["log_file_name"]

    filepath = os.path.join(logs_dir, filename)

    # New message entry
    new_message = {
        "user_message": entry["user_message"],
        "bot_reply": entry["bot_reply"],
        "timestamp": datetime.utcnow().isoformat()
    }

    # Append or create log
    if os.path.exists(filepath):
        with open(filepath, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data["messages"].append(new_message)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    else:
        data = {
            "event": "chat",
            "mobile": entry["mobile"],
            "name": entry["name"],
            "client_name": entry["client_name"],
            "company": entry["company"],
            "industry": entry["industry"],
            "messages": [new_message]
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# ---- Per-chat JSON helpers ----
def _now_iso():
    return datetime.utcnow().isoformat()

def _safe_token(value, fallback="chat"):
    value = str(value or fallback).strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    return value[:60] or fallback

def _chat_filename(chat_id):
    chat_id = _safe_token(chat_id, "chat")
    if not chat_id.endswith(".json"):
        chat_id += ".json"
    return os.path.basename(chat_id)

def _chat_path(chat_id):
    return os.path.join(CHAT_LOGS_DIR, _chat_filename(chat_id))

def _safe_original_filename(value, fallback="attachment"):
    """Return a safe user-facing basename while preserving Unicode/spaces/punctuation."""
    text = str(value or "").replace("\\", "/")
    text = text.split("/")[-1]
    text = "".join(ch for ch in text if ch not in "\x00\r\n")
    text = text.strip()
    if text in {"", ".", ".."}:
        text = str(fallback or "attachment").replace("\\", "/").split("/")[-1].strip() or "attachment"
    # Keep common filesystem limits reasonable without changing normal names.
    return text[:255]

def _iter_attachment_records(chat):
    if not isinstance(chat, dict):
        return
    for att in chat.get("attachments") or []:
        if isinstance(att, dict):
            yield att
    for msg in chat.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        for att in msg.get("attachments") or []:
            if isinstance(att, dict):
                yield att

def _find_original_filename_for_stored(stored_filename):
    """Resolve a stored chat attachment back to its original download filename."""
    stored = os.path.basename(stored_filename or "")
    if not stored or not os.path.isdir(CHAT_LOGS_DIR):
        return stored or "attachment"
    for json_name in os.listdir(CHAT_LOGS_DIR):
        if not json_name.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(CHAT_LOGS_DIR, json_name), "r", encoding="utf-8") as f:
                chat = json.load(f)
        except Exception:
            continue
        for att in _iter_attachment_records(chat):
            candidate = os.path.basename(att.get("stored_filename") or att.get("storedFilename") or "")
            if candidate != stored:
                continue
            original = (
                att.get("original_filename")
                or att.get("filename")
                or att.get("name")
                or att.get("relative_path")
                or att.get("relativePath")
                or stored
            )
            return _safe_original_filename(original, stored)
    return stored


def _attachment_belongs_to_user(stored_filename, username):
    stored = os.path.basename(stored_filename or "")
    expected_user = str(username or "")
    if not stored or not expected_user or not os.path.isdir(CHAT_LOGS_DIR):
        return False
    for json_name in os.listdir(CHAT_LOGS_DIR):
        if not json_name.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(CHAT_LOGS_DIR, json_name), "r", encoding="utf-8") as f:
                chat = json.load(f)
        except Exception:
            continue
        chat_user = str(chat.get("user") or chat.get("name") or "") if isinstance(chat, dict) else ""
        if chat_user != expected_user:
            continue
        if any(
            os.path.basename(att.get("stored_filename") or att.get("storedFilename") or "") == stored
            for att in _iter_attachment_records(chat)
        ):
            return True
    return False

def _attachment_basename_for_chat(chat):
    """Use the chat JSON filename as the attachment filename prefix."""
    chat_id = (chat or {}).get("chat_id") or (chat or {}).get("filename") or _new_chat_id("User")
    return os.path.splitext(_chat_filename(chat_id))[0]

def _attachment_urls(stored_filename):
    safe = os.path.basename(stored_filename or "")
    quoted = quote(safe)
    return {
        "preview_url": public_path(f"/history/attachment/{quoted}"),
        "download_url": public_path(f"/history/attachment/{quoted}?download=1"),
    }

def _is_stored_attachment_name(filename):
    safe = os.path.basename(filename or "")
    return bool(re.match(r"^[A-Za-z0-9._-]+_doc_\d+(?:\.[A-Za-z0-9]+)?$", safe))

def _clean_attachment_ext(filename):
    ext = os.path.splitext(os.path.basename(filename or ""))[1].lower()
    ext = re.sub(r"[^.a-z0-9]", "", ext)
    if len(ext) > 16:
        ext = ext[:16]
    return ext if ext.startswith(".") else ""

def _next_attachment_doc_index(chat):
    """Return the next _doc_x number for files saved beside this chat JSON."""
    base = _attachment_basename_for_chat(chat or {})
    highest = 0
    for att in (chat or {}).get("attachments") or []:
        try:
            highest = max(highest, int(att.get("doc_index") or 0))
        except Exception:
            pass
        stored = att.get("stored_filename") or ""
        m = re.match(rf"^{re.escape(base)}_doc_(\d+)(?:\.[A-Za-z0-9]+)?$", os.path.basename(stored))
        if m:
            highest = max(highest, int(m.group(1)))
    if os.path.isdir(CHAT_LOGS_DIR):
        pattern = re.compile(rf"^{re.escape(base)}_doc_(\d+)(?:\.[A-Za-z0-9]+)?$", re.IGNORECASE)
        for filename in os.listdir(CHAT_LOGS_DIR):
            m = pattern.match(filename)
            if m:
                highest = max(highest, int(m.group(1)))
    return highest + 1

def _normalize_attachment_urls(att):
    if not isinstance(att, dict):
        return att
    stored = os.path.basename(att.get("stored_filename") or att.get("storedFilename") or "")
    fallback_original = (
        att.get("original_filename")
        or att.get("filename")
        or att.get("name")
        or att.get("relative_path")
        or att.get("relativePath")
        or stored
        or "attachment"
    )
    original_name = _safe_original_filename(fallback_original, stored or "attachment")
    att.setdefault("original_filename", original_name)
    att.setdefault("filename", original_name)
    if stored and _is_stored_attachment_name(stored):
        urls = _attachment_urls(stored)
        att["stored_filename"] = stored
        att.setdefault("preview_url", urls["preview_url"])
        att.setdefault("download_url", urls["download_url"])
        # Backward-compatible aliases used by older frontend code.
        att.setdefault("url", urls["preview_url"])
    return att

def _normalize_chat_attachments(chat):
    if not isinstance(chat, dict):
        return chat
    chat["attachments"] = [_normalize_attachment_urls(att) for att in (chat.get("attachments") or [])]
    for msg in chat.get("messages", []) or []:
        if isinstance(msg, dict) and msg.get("attachments"):
            msg["attachments"] = [_normalize_attachment_urls(att) for att in msg.get("attachments") or []]
    return chat

def _new_chat_id(username="User"):
    stamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    return f"chat_{_safe_token(username, 'User')}_{stamp}_{uuid4().hex[:8]}"

def _count_attachments_in_chat(chat):
    """Return the number of attachments saved inside this single chat JSON."""
    attachments = chat.get("attachments") or []
    if isinstance(attachments, list):
        return len(attachments)
    return 0



def _has_real_credentials(chat_or_credentials):
    """Return True when the chat has client credentials beyond the default auto-fill values."""
    data = chat_or_credentials or {}
    client_name = str(data.get("client_name") or data.get("name") or "").strip()
    company = str(data.get("company") or "").strip()
    industry = str(data.get("industry") or "").strip()
    mobile = str(data.get("mobile") or "").strip()

    default_values = {"", "auto-fill", "autofill", "n/a", "na", "none", "unknown"}

    has_client = client_name.lower() not in default_values and client_name.lower() != str(data.get("user") or "").strip().lower()
    has_company = company.lower() not in default_values and company.lower() != "jormall"
    has_industry = industry.lower() not in default_values
    has_mobile = mobile.lower() not in default_values

    return bool(has_client or has_company or has_industry or has_mobile)

def _sidebar_chat_title(chat_or_credentials, is_current=False):
    base = "Current Chat" if is_current else "Previous Chat"
    if _has_real_credentials(chat_or_credentials):
        return f"{base} (with credentials)"
    return base

def _next_attachment_chat_sequence(username="User"):
    """
    Find the next attachment chat number for this user.
    Example filename: admin_2026-06-25T10-30-00_attachment_1_.json
    """
    safe_user = _safe_token(username, "User")
    pattern = re.compile(rf"^{re.escape(safe_user)}_.*_attachment_(\d+)_\.json$", re.IGNORECASE)
    highest = 0
    if os.path.isdir(CHAT_LOGS_DIR):
        for filename in os.listdir(CHAT_LOGS_DIR):
            match = pattern.match(filename)
            if match:
                try:
                    highest = max(highest, int(match.group(1)))
                except ValueError:
                    pass
    return highest + 1

def _attachment_chat_id(username="User", created_at=None):
    safe_user = _safe_token(username, "User")
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")) if created_at else datetime.utcnow()
    except Exception:
        dt = datetime.utcnow()
    stamp = dt.strftime("%Y-%m-%dT%H-%M-%S")
    seq = _next_attachment_chat_sequence(username)
    chat_id = f"{safe_user}_{stamp}_attachment_{seq}_"
    while os.path.exists(_chat_path(chat_id)):
        seq += 1
        chat_id = f"{safe_user}_{stamp}_attachment_{seq}_"
    return chat_id

def _trim_text(text, limit):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[Text truncated to keep this chat JSON manageable.]"

def _decode_text_bytes(raw):
    for enc in ("utf-8", "utf-8-sig", "cp1256", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")

def _extract_xlsx_text(raw):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(raw), read_only=True, data_only=True)
        lines = []
        for ws in wb.worksheets[:8]:
            lines.append(f"[Sheet: {ws.title}]")
            for row in ws.iter_rows(max_row=250, values_only=True):
                vals = [str(v) for v in row if v is not None]
                if vals:
                    lines.append(" | ".join(vals))
        return "\n".join(lines), "extracted"
    except Exception as e:
        return "", f"xlsx extraction failed: {e}"

def _extract_attachment_text(filename, raw):
    ext = os.path.splitext(filename or "")[1].lower()
    try:
        if ext == ".pdf":
            doc = fitz.open(stream=raw, filetype="pdf")
            return "\n".join(page.get_text() for page in doc), "extracted"
        if ext == ".docx":
            doc = Document(BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip()), "extracted"
        if ext in {".txt", ".md", ".csv", ".json", ".html", ".htm", ".css", ".js", ".py", ".sql", ".xml", ".log"}:
            return _decode_text_bytes(raw), "extracted"
        if ext in {".xlsx", ".xlsm"}:
            return _extract_xlsx_text(raw)
        return "", "metadata only: unsupported binary or media file type"
    except Exception as e:
        return "", f"extraction failed: {e}"

def _read_uploaded_attachments(files, relative_paths=None, chat=None):
    """
    Save each uploaded file in the same logs folder as the chat JSON.
    Filename pattern: <chat_json_name_without_ext>_doc_<x>.<ext>
    Folder uploads arrive as separate files, so each folder item receives its own _doc_x index.
    """
    attachments = []
    relative_paths = relative_paths or []
    chat = chat or {}
    base_name = _attachment_basename_for_chat(chat)
    next_index = _next_attachment_doc_index(chat)

    for idx, f in enumerate(files or []):
        if not f or not getattr(f, "filename", ""):
            continue
        raw = f.read()
        original_name = _safe_original_filename(f.filename, "attachment")
        relative_path = relative_paths[idx] if idx < len(relative_paths) and relative_paths[idx] else f.filename
        ext = _clean_attachment_ext(original_name or relative_path)

        doc_index = next_index
        stored_filename = f"{base_name}_doc_{doc_index}{ext}"
        while os.path.exists(os.path.join(CHAT_LOGS_DIR, stored_filename)):
            doc_index += 1
            stored_filename = f"{base_name}_doc_{doc_index}{ext}"
        next_index = doc_index + 1

        stored_path = os.path.join(CHAT_LOGS_DIR, stored_filename)
        with open(stored_path, "wb") as out:
            out.write(raw)

        text, status = _extract_attachment_text(original_name or relative_path, raw)
        urls = _attachment_urls(stored_filename)
        attachments.append({
            "attachment_id": uuid4().hex[:12],
            "doc_index": doc_index,
            "filename": original_name,
            "original_filename": original_name,
            "relative_path": relative_path,
            "stored_filename": stored_filename,
            "saved_in": "logs",
            "content_type": getattr(f, "mimetype", None) or "application/octet-stream",
            "size_bytes": len(raw),
            "extract_status": status,
            "extracted_text": _trim_text(text, MAX_ATTACHMENT_TEXT_CHARS),
            "preview_url": urls["preview_url"],
            "download_url": urls["download_url"],
            "url": urls["preview_url"],
            "uploaded_at": _now_iso()
        })
    return attachments

def _blank_chat(chat_id, username, credentials):
    return {
        "event": "chat",
        "version": 2,
        "chat_id": chat_id,
        "filename": _chat_filename(chat_id),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "user": username,
        "name": username,
        "client_name": credentials.get("client_name") or credentials.get("name") or "Auto-fill",
        "company": credentials.get("company") or "JorMall",
        "industry": credentials.get("industry") or "Auto-fill",
        "mobile": credentials.get("mobile") or "N/A",
        "title": _sidebar_chat_title(credentials, is_current=True),
        "has_attachments": False,
        "attachment_count": 0,
        "attachments": [],
        "messages": []
    }

def _load_or_create_chat(chat_id, username, credentials):
    if chat_id:
        path = _chat_path(chat_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Upgrade old files enough for the frontend/backend to use them.
            data.setdefault("version", 2)
            data.setdefault("chat_id", os.path.splitext(os.path.basename(path))[0])
            data.setdefault("filename", os.path.basename(path))
            data.setdefault("messages", [])
            data.setdefault("attachments", [])
            data.setdefault("attachment_count", _count_attachments_in_chat(data))
            data.setdefault("has_attachments", any(m.get("attachments") for m in data.get("messages", []) if isinstance(m, dict)) or data.get("attachment_count", 0) > 0)
            _normalize_chat_attachments(data)
            return data
    new_id = _new_chat_id(username)
    return _blank_chat(new_id, username, credentials)

def _save_chat(chat):
    """Save the chat JSON without renaming it when attachments are added."""
    if not chat.get("chat_id"):
        chat["chat_id"] = _new_chat_id(chat.get("user") or chat.get("name") or "User")

    chat["updated_at"] = _now_iso()
    chat["title"] = _sidebar_chat_title(chat, is_current=True)
    _normalize_chat_attachments(chat)

    chat["attachment_count"] = _count_attachments_in_chat(chat)
    chat["has_attachments"] = chat["attachment_count"] > 0 or any(
        isinstance(m, dict) and m.get("attachments") for m in chat.get("messages", [])
    )

    chat["filename"] = _chat_filename(chat.get("chat_id"))
    new_path = _chat_path(chat["chat_id"])
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(chat, f, ensure_ascii=False, indent=2)

def _attachment_context(attachments, limit=MAX_CHAT_ATTACHMENT_CONTEXT_CHARS):
    parts = []
    used = 0
    for att in attachments or []:
        text = att.get("extracted_text") or ""
        header = (
            f"Attachment: {att.get('relative_path') or att.get('filename')}\n"
            f"Type: {att.get('content_type')} | Size: {att.get('size_bytes')} bytes | Status: {att.get('extract_status')}\n"
        )
        block = header + (text if text else "[No readable text extracted; metadata is available only.]")
        remaining = limit - used
        if remaining <= 0:
            break
        block = block[:remaining]
        parts.append(block)
        used += len(block)
    return "\n\n---\n\n".join(parts)

def _message_to_openai(msg):
    role = msg.get("role")
    if role not in {"user", "assistant"}:
        return None
    if role == "assistant":
        content = msg.get("bot_reply") or msg.get("content") or ""
    else:
        content = msg.get("user_message") or msg.get("content") or ""
        atts = msg.get("attachments") or []
        if atts:
            content += "\n\n[Attachments attached to this message:]\n" + _attachment_context(atts)
    if not content.strip():
        return None
    return {"role": role, "content": content}

def _build_chat_messages(chat, current_user_prompt):
    messages = [SYSTEM_PROMPT]
    old_messages = chat.get("messages", [])[-MAX_CHAT_HISTORY_MESSAGES:]
    for old in old_messages:
        converted = _message_to_openai(old) if isinstance(old, dict) else None
        if converted:
            messages.append(converted)
    messages.append({"role": "user", "content": current_user_prompt})
    return messages

# ---- Flask App ----
app = Flask(__name__, static_folder=STATIC_FOLDER)
# Respect the public HTTPS scheme/host supplied by Nginx or another trusted reverse proxy.
# This prevents generated links and redirects from falling back to the internal HTTP host.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or str(uuid.uuid4())

# Session Configuration
app.config["SESSION_TYPE"] = "filesystem"  # Or 'redis', 'sqlalchemy', etc.
app.config["SESSION_FILE_DIR"] = os.path.join(BASE_DIR, "flask_sessions")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
# The central login endpoint is served on jormallapp.com while protected apps
# live on subdomains. Share only the signed session cookie across that domain.
session_cookie_domain = os.getenv("SESSION_COOKIE_DOMAIN", ".jormallapp.com").strip().strip('"').strip("'")
app.config["SESSION_COOKIE_DOMAIN"] = session_cookie_domain or None
app.config["SESSION_COOKIE_SECURE"] = os.getenv(
    "SESSION_COOKIE_SECURE", "true"
).strip().lower() not in {"0", "false", "no", "off"}
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

Session(app)  # Then bind it to the app

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    CORS(app, supports_credentials=True, origins=cors_origins)
app.register_blueprint(sms_bitly_bp)


def session_login_required(f):
    """Protect routes declared before the directory-backed auth helpers below."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in") or not session.get("username"):
            return jsonify({"error": "Not authorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ---- DOCUMENT DOWNLOAD ROUTE (MUST BE FIRST TO AVOID BEING SHADOWED) ----

@app.route('/documents/<path:filename>')
@session_login_required
def download_document(filename):
    full_path = os.path.join(DOCUMENTS_FOLDER, filename)
    print(f"Requested document: {filename}")
    print(f"Full path: {full_path}")
    if not os.path.isfile(full_path):
        print("File not found")
    return send_from_directory(DOCUMENTS_FOLDER, filename, as_attachment=True)


@app.route('/history/attachment/<path:filename>')
@session_login_required
def serve_chat_attachment(filename):
    safe_name = os.path.basename(filename)
    if not _is_stored_attachment_name(safe_name):
        abort(404)
    if not _attachment_belongs_to_user(safe_name, session.get("username")):
        abort(404)
    path = os.path.join(CHAT_LOGS_DIR, safe_name)
    if not os.path.isfile(path):
        abort(404)
    as_download = request.args.get("download") in {"1", "true", "yes"}
    download_name = _find_original_filename_for_stored(safe_name) if as_download else None
    return send_from_directory(
        CHAT_LOGS_DIR,
        safe_name,
        as_attachment=as_download,
        download_name=download_name,
    )


# ---- Debug Test Endpoint ----

@app.route("/build-version")
def build_version():
    return jsonify({"build": "NO_SHORTCUTS_REPORT_EXPLAINER_ONLY_V3", "shortcut_panel": "removed", "arabic_docx": "rtl_right_aligned"})

@app.route("/healthz")
def healthcheck():
    return jsonify({"status": "ok"})

@app.route("/readyz")
def readiness_check():
    checks = {
        "openai_api_key": bool(OPENAI_API_KEY),
        "flask_secret_key": bool(os.getenv("FLASK_SECRET_KEY")),
        "user_directory_token": bool(user_directory_token()),
        "documents": bool(document_records),
    }
    status_code = 200 if all(checks.values()) else 503
    return jsonify({"status": "ready" if status_code == 200 else "not_ready", "checks": checks}), status_code


# ---- Serve Complete Assets Tree ----
@app.route("/assets/<path:filename>")
@session_login_required
def serve_assets(filename):
    return send_from_directory(ASSETS_DIR, filename)

# ---- Serve Images ----
@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)
# ---- Serve Videos ----
@app.route("/videos/<path:filename>")
@session_login_required
def serve_video(filename):
    path = os.path.join(VIDEOS_DIR, filename)

    if not os.path.exists(path):
        abort(404)

    range_header = request.headers.get('Range', None)
    if not range_header:
        return send_file(path)

    size = os.path.getsize(path)
    byte1, byte2 = 0, None

    m = re.search(r'bytes=(\d+)-(\d*)', range_header)
    if m:
        byte1 = int(m.group(1))
        if m.group(2):
            byte2 = int(m.group(2))

    length = size - byte1
    if byte2 is not None:
        length = byte2 - byte1 + 1

    with open(path, 'rb') as f:
        f.seek(byte1)
        data = f.read(length)

    resp = Response(data, 206, mimetype='video/mp4', direct_passthrough=True)
    resp.headers.add('Content-Range', f'bytes {byte1}-{byte1 + length - 1}/{size}')
    resp.headers.add('Accept-Ranges', 'bytes')
    resp.headers.add('Content-Length', str(length))
    return resp
# ---- Serve Presentations ----
@app.route("/presentations/<path:filename>")
@session_login_required
def serve_presentation(filename):
    return send_from_directory(PRST_DIR, filename)
# ---- Serve SMA Documents ----
@app.route("/SMA_documents/<path:filename>")
@session_login_required
def serve_sma_documents(filename):
    return send_from_directory(SMADOC_DIR, filename)
# ---- Serve Fonts ----
@app.route('/fonts/<path:filename>')
def custom_fonts(filename):
    return send_from_directory(FONTS_DIR, filename)
# ---- Serve Static Files ----
@app.route('/static/<path:filename>')
def serve_static_files(filename):
    return send_from_directory(STATIC_FOLDER, filename)

# ---- Serve Home Page ----
@app.route("/")
def serve_jormall_assistant_index():
    return app.send_static_file("index.html")

# ---- Serve Sales Script sidebar ----
@app.route('/sales-script')
@session_login_required
def sales_script():
    return send_from_directory(STATIC_FOLDER, 'sales_call_script.html')

# ---- Embedding Analysis API ----
def _preview_text(text, limit=180):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit] + ("..." if len(text) > limit else "")

def _pca_project_2d(matrix):
    """Project embedding vectors to 2D using NumPy-only PCA."""
    X = np.asarray(matrix, dtype=float)
    if X.ndim != 2 or X.shape[0] == 0:
        return np.empty((0, 2))
    if X.shape[0] == 1:
        return np.zeros((1, 2))

    X = np.nan_to_num(X, copy=False)
    X_centered = X - X.mean(axis=0, keepdims=True)
    try:
        _u, _s, vh = np.linalg.svd(X_centered, full_matrices=False)
        components = vh[:2].T
        coords = X_centered @ components
        if coords.shape[1] == 1:
            coords = np.column_stack([coords[:, 0], np.zeros(coords.shape[0])])
        return coords[:, :2]
    except Exception as e:
        print(f"[WARN] PCA projection failed: {e}")
        return np.column_stack([np.arange(X.shape[0], dtype=float), np.zeros(X.shape[0])])

def _kmeans_2d(coords, k=None, max_iter=30):
    coords = np.asarray(coords, dtype=float)
    n = coords.shape[0]
    if n == 0:
        return np.array([], dtype=int), np.empty((0, 2))
    if n < 4:
        return np.zeros(n, dtype=int), np.array([coords.mean(axis=0)])

    if k is None:
        k = int(round(np.sqrt(n / 2)))
        k = max(2, min(8, k, n))

    order = np.argsort(coords[:, 0])
    picks = np.linspace(0, n - 1, k).round().astype(int)
    centroids = coords[order[picks]].copy()

    labels = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        distances = np.linalg.norm(coords[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = distances.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster_id in range(k):
            members = coords[labels == cluster_id]
            if len(members):
                centroids[cluster_id] = members.mean(axis=0)
    return labels, centroids

def _cosine_pair_stats(vectors, max_pairs_items=350):
    if len(vectors) < 2:
        return {"average_cosine_similarity": None, "duplicate_like_pairs": []}

    X = np.asarray(vectors[:max_pairs_items], dtype=float)
    X = np.nan_to_num(X, copy=False)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1
    Xn = X / norms
    sim = Xn @ Xn.T
    upper = sim[np.triu_indices(sim.shape[0], k=1)]
    avg = float(np.mean(upper)) if upper.size else None

    duplicate_like_pairs = []
    rows, cols = np.where(np.triu(sim, k=1) >= 0.94)
    for i, j in zip(rows[:25], cols[:25]):
        duplicate_like_pairs.append({
            "first_index": int(i),
            "second_index": int(j),
            "similarity": round(float(sim[i, j]), 4)
        })
    return {
        "average_cosine_similarity": round(avg, 4) if avg is not None else None,
        "duplicate_like_pairs": duplicate_like_pairs
    }

def _embedding_recommendations(total_chunks, avg_similarity, duplicate_count, outlier_count, source_count):
    recs = []
    if total_chunks < 20:
        recs.append("The knowledge base has few chunks. Add more official documents before relying heavily on RAG answers.")
    elif total_chunks > 700:
        recs.append("The knowledge base is large. Keep top-k at 20 for now, but consider metadata filters by document type or department.")
    else:
        recs.append("Top-k = 20 with cosine similarity is a reasonable default for this chatbot size.")

    if avg_similarity is not None:
        if avg_similarity > 0.82:
            recs.append("Many chunks are very similar. Remove repeated paragraphs or split policy templates more cleanly.")
        elif avg_similarity < 0.18 and source_count > 1:
            recs.append("The documents are semantically scattered. Add source labels in prompts or separate collections by topic if answers become mixed.")

    if duplicate_count:
        recs.append("Review near-duplicate chunks because they can make the chatbot repeat the same answer and reduce retrieval diversity.")
    if outlier_count:
        recs.append("Review outlier chunks. They may be useful unique content, or they may be badly extracted text/noise.")
    if not recs:
        recs.append("The embedding map looks balanced. Continue testing with real user questions and compare retrieved chunks.")
    return recs

@app.route("/api/embedding-analysis", methods=["GET"])
@session_login_required
def embedding_analysis():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Not authorized"}), 401
    if session.get("username") not in AI_ANALYTICS_USERS:
        return jsonify({"success": False, "error": "AI Analytics is restricted to approved admin users."}), 403

    records = list(iter_embedded_records())
    limit = request.args.get("limit", "700")
    try:
        limit = max(20, min(1200, int(limit)))
    except Exception:
        limit = 700

    if not records:
        return jsonify({
            "success": False,
            "error": "No embeddings are currently loaded. Add documents and make sure OPENAI_API_KEY is configured, then restart the app."
        }), 503

    records = records[:limit]
    vectors = [np.asarray(r.get("embedding"), dtype=float) for r in records]
    dims = int(vectors[0].shape[0]) if vectors and vectors[0].ndim == 1 else 0
    coords = _pca_project_2d(vectors)
    labels, _centroids = _kmeans_2d(coords)

    distances = np.linalg.norm(coords - coords.mean(axis=0, keepdims=True), axis=1) if len(coords) else np.array([])
    outlier_threshold = float(distances.mean() + 1.5 * distances.std()) if len(distances) > 3 else float("inf")
    outlier_indices = set(np.where(distances > outlier_threshold)[0].tolist()) if len(distances) else set()

    pair_stats = _cosine_pair_stats(vectors)
    duplicate_pairs = pair_stats["duplicate_like_pairs"]
    avg_similarity = pair_stats["average_cosine_similarity"]

    sources = sorted(set(str(r.get("source") or "Knowledge base") for r in records))
    points = []
    for idx, (record, xy) in enumerate(zip(records, coords)):
        source = str(record.get("source") or "Knowledge base")
        points.append({
            "id": str(record.get("id") or f"chunk_{idx + 1}"),
            "x": round(float(xy[0]), 6),
            "y": round(float(xy[1]), 6),
            "source": source,
            "chunk_index": int(record.get("chunk_index") or idx + 1),
            "cluster": int(labels[idx]) if len(labels) else 0,
            "word_count": int(record.get("word_count") or len(str(record.get("chunk") or "").split())),
            "preview": _preview_text(record.get("chunk"), 220),
            "is_outlier": idx in outlier_indices,
            "distance_from_center": round(float(distances[idx]), 6) if len(distances) else 0
        })

    cluster_summaries = []
    for cluster_id in sorted(set(int(x) for x in labels.tolist())) if len(labels) else [0]:
        member_indices = [i for i, label in enumerate(labels) if int(label) == cluster_id]
        source_counts = {}
        for i in member_indices:
            source_counts[points[i]["source"]] = source_counts.get(points[i]["source"], 0) + 1
        top_sources = sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        cluster_summaries.append({
            "cluster": cluster_id,
            "size": len(member_indices),
            "top_sources": [{"source": name, "count": count} for name, count in top_sources],
            "sample_preview": points[member_indices[0]]["preview"] if member_indices else ""
        })

    outliers = sorted(
        [points[i] for i in outlier_indices],
        key=lambda p: p.get("distance_from_center", 0),
        reverse=True
    )[:12]

    duplicate_like_chunks = []
    for pair in duplicate_pairs[:12]:
        i = pair["first_index"]
        j = pair["second_index"]
        if i < len(points) and j < len(points):
            duplicate_like_chunks.append({
                "similarity": pair["similarity"],
                "first": {"source": points[i]["source"], "chunk_index": points[i]["chunk_index"], "preview": points[i]["preview"]},
                "second": {"source": points[j]["source"], "chunk_index": points[j]["chunk_index"], "preview": points[j]["preview"]}
            })

    recommendations = _embedding_recommendations(
        total_chunks=len(records),
        avg_similarity=avg_similarity,
        duplicate_count=len(duplicate_like_chunks),
        outlier_count=len(outliers),
        source_count=len(sources)
    )

    return jsonify({
        "success": True,
        "points": points,
        "summary": {
            "total_documents": len(sources),
            "total_chunks": len(records),
            "loaded_chunk_limit": limit,
            "embedding_dimension": dims,
            "embedding_model": RAG_EMBEDDING_MODEL,
            "top_k": RAG_TOP_K,
            "similarity_function": RAG_SIMILARITY_FUNCTION,
            "projection": RAG_PROJECTION_METHOD,
            "average_cosine_similarity": avg_similarity
        },
        "analysis": {
            "clusters": cluster_summaries,
            "outliers": outliers,
            "duplicate_like_chunks": duplicate_like_chunks,
            "recommendations": recommendations
        }
    })

# ---- Login HTML----

@app.route("/api/website-context", methods=["POST"])
@session_login_required
def website_context():
    """Fetch a small amount of public website text for the Sales Assistant website/client analyzer."""
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    max_length = int(data.get("maxLength") or 4500)

    if not url:
        return jsonify({"error": "Website URL is required."}), 400

    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", url, re.IGNORECASE):
        return jsonify({"error": "Please enter a valid website URL."}), 400

    try:
        extracted_text = fetch_website_text(url, max_length=max(800, min(max_length, 8000)))
        if not extracted_text or extracted_text.startswith("[Error fetching"):
            return jsonify({
                "url": url,
                "text": "",
                "warning": extracted_text or "No readable website text was found."
            })
        return jsonify({"url": url, "text": extracted_text})
    except Exception as e:
        print("Website context fetch error:", e)
        return jsonify({"error": f"Failed to read website content: {str(e)}"}), 500


def user_directory_token():
    token = (os.getenv("USER_DIRECTORY_TOKEN") or "").strip().strip('"').strip("'")
    if token:
        return token
    try:
        with open(USER_DIRECTORY_TOKEN_FILE, "r", encoding="utf-8") as token_file:
            return token_file.read().strip().strip('"').strip("'")
    except OSError:
        return ""


def user_directory_request(path, method="GET", payload=None):
    token = user_directory_token()
    if not token:
        return {"success": False, "error": "User directory is not configured."}, 503
    try:
        response = requests.request(
            method,
            f"{USER_DIRECTORY_URL}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        try:
            data = response.json()
        except ValueError:
            data = {"success": False, "error": "Invalid response from user directory."}
        return data, response.status_code
    except requests.RequestException:
        return {"success": False, "error": "User directory is temporarily unavailable."}, 503


def refresh_session_user():
    username = str(session.get("username") or "")
    if not session.get("logged_in") or not username:
        return None
    identity = {"id": session.get("user_id")} if session.get("user_id") else {"identifier": username}
    directory_data, directory_status = user_directory_request("/status", "POST", identity)
    if directory_status != 200 or not directory_data.get("success"):
        session.clear()
        return None
    user = directory_data.get("user") or {}
    previous_version = session.get("auth_version")
    current_version = user.get("updated_at")
    if previous_version and current_version and previous_version != current_version:
        session.clear()
        return None
    session["user_id"] = user.get("id")
    session["auth_version"] = current_version
    session["email"] = user.get("email") or ""
    session["role"] = user.get("role") or "user"
    session["allowed_categories"] = user.get("categories") or ["General"]
    return user


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or data.get("email") or "").strip()
    password = data.get("password", "")
    directory_data, directory_status = user_directory_request(
        "/verify", "POST", {"identifier": username, "password": password}
    )
    if directory_status == 200 and directory_data.get("success"):
        user = directory_data.get("user") or {}
        canonical_username = str(user.get("username") or username)
        allowed_categories = user.get("categories") or ["General"]
        session["logged_in"] = True
        session["username"] = canonical_username
        session["user_id"] = user.get("id")
        session["auth_version"] = user.get("updated_at")
        session["email"] = user.get("email") or ""
        session["role"] = user.get("role") or "user"
        session["allowed_categories"] = allowed_categories
        log_admin_activity(username=canonical_username, action="login")
        return jsonify({
            "success": True,
            "username": canonical_username,
            "email": user.get("email") or "",
            "is_admin": session["role"] == "admin",
            "allowed_categories": allowed_categories,
            "auto_fill_credentials": "Non-Credentials Login" in allowed_categories,
            "can_ai_analytics": canonical_username in AI_ANALYTICS_USERS,
        })
    if directory_status == 401:
        return jsonify({"success": False, "error": "Invalid username/email or password"}), 401
    return jsonify(directory_data), directory_status

@app.route("/sso/verify", methods=["GET"])
def sso_verify():
    user = refresh_session_user()
    if user is None:
        return jsonify({"success": False, "error": "Not authorized"}), 401
    username = str(user.get("username") or session.get("username") or "")
    is_admin = user.get("role") == "admin"
    response = jsonify({
        "success": True,
        "username": username,
        "email": session.get("email", ""),
        "is_admin": is_admin,
        "allowed_categories": session.get("allowed_categories", ["General"]),
        "auto_fill_credentials": "Non-Credentials Login" in session.get("allowed_categories", []),
        "can_ai_analytics": username in AI_ANALYTICS_USERS,
    })
    response.headers["X-SSO-User"] = username
    response.headers["X-SSO-Admin"] = "1" if is_admin else "0"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/sso/verify-admin", methods=["GET"])
def sso_verify_admin():
    user = refresh_session_user()
    if user is None:
        return jsonify({"success": False, "error": "Not authorized"}), 401
    username = str(user.get("username") or session.get("username") or "")
    if user.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403
    response = jsonify({"success": True, "username": username, "is_admin": True})
    response.headers["X-SSO-User"] = username
    response.headers["X-SSO-Admin"] = "1"
    response.headers["Cache-Control"] = "no-store"
    return response


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if refresh_session_user() is None:
            return jsonify({"error": "Not authorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Require a current directory-backed administrator session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = refresh_session_user()
        if user is None:
            return jsonify({"success": False, "error": "Not authorized"}), 401
        if user.get("role") != "admin":
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    response = jsonify({"success": True})
    # Remove the host-only cookie issued by the previous release as well as the
    # shared-domain cookie that Flask-Session expires after this response.
    response.delete_cookie(
        app.config.get("SESSION_COOKIE_NAME", "session"),
        path=app.config.get("SESSION_COOKIE_PATH", "/") or "/",
        domain=None,
        secure=app.config.get("SESSION_COOKIE_SECURE", True),
        httponly=app.config.get("SESSION_COOKIE_HTTPONLY", True),
        samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
    )
    return response


@app.route("/chat/new", methods=["POST"])
@login_required
def new_chat():
    session.pop("current_chat_id", None)
    return jsonify({"success": True})

# ---- System Prompt ----
SYSTEM_PROMPT = {
    "role": "system",
    "content": """
You are a professional assistant for JorMall, Jordan’s licensed SMS marketing provider.

Your expertise is strictly within:
- SMS marketing and campaign strategies
- JorMall's bulk SMS platform and API
- JorMall’s loyalty program Niqaty
- Client targeting, segmentation, and message personalization
- Regulatory compliance (e.g., TRC rules)
- SMS delivery performance and cost analysis
- Competitive comparison (SMS vs other channels), only to explain the strengths of SMS
- JorMall Interactive Campaign Chatbot and its approved hosting packages
- JorMall Organization AI Assistant and its approved hosting packages

🧠 Your Responsibilities:
- Only answer using the provided knowledge-base context (RAG) and any attached-file context supplied with the user message. Do not infer or invent information beyond those sources.
- When replying, always include at least 2–3 sentences verbatim or clearly paraphrased from the retrieved documents that directly support the answer.
- If multiple documents are referenced, try to distinguish which information comes from which (if the document title or section is available).
- Use bullet points, tables, or Markdown formatting for clarity when helpful.

🌐 Language & Translation:
- You may reply in Arabic or English based on the user’s input.
- If the user requests a translation of the previous reply, provide it using this format:
  - 🇺🇸 **English Translation:** …
  - 🇯🇴 **الترجمة العربية:** …
- Do not offer translation unless explicitly requested.

💬 Response Behavior:
- Keep responses professional and clearly formatted.
- For general, exploratory, or product-wide questions (e.g., "What SMS services do you offer?"), provide **detailed summaries** of all relevant services, including: key features, common use cases, compliance requirements, and client obligations.
- Use **bullet points**, **tables**, or **headings** to improve structure and readability.
- For shorter or campaign-oriented questions (e.g., "Which SMS type suits feedback collection?"), provide focused but still informative answers using content from the source.


❗ When Not to Answer:
If a question is unrelated to messaging, SMS delivery, or the approved JorMall chatbot and AI assistant products listed above (e.g., logistics, hardware, unrelated software), respond with:
> "I'm here to assist with SMS marketing and messaging-related inquiries only. For anything else, please contact JorMall at info@jormall.com or +962 6 5855703."

If the requested information is not available in the knowledge base or context, respond with:
> "Based on our current knowledge base, I do not have this information. For further assistance, please contact JorMall."
 
Always maintain a professional tone, remain helpful, and guide users toward the most relevant information from JorMall’s official resources.
"""}


# ---- Chat Logic ----
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    # Supports normal JSON messages and multipart messages with attachments.
    uploaded_files = []
    relative_paths = []
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        user_msg = (request.form.get("message") or "").strip()
        chat_id = (request.form.get("chat_id") or request.form.get("chat_filename") or "").strip()
        try:
            credentials = json.loads(request.form.get("credentials") or "{}")
        except Exception:
            credentials = {}
        try:
            relative_paths = json.loads((request.form.get("relative_paths") or request.form.get("attachment_paths") or "[]"))
        except Exception:
            relative_paths = []
        uploaded_files = request.files.getlist("attachments")
    else:
        data = request.json or {}
        user_msg = data.get("message", "").strip()
        credentials = data.get("credentials", {}) or {}
        chat_id = (data.get("chat_id") or data.get("chat_filename") or "").strip()

    # Keep using the currently opened chat if the frontend does not send chat_id.
    # This prevents creating a new JSON chat log on every prompt.
    if not chat_id:
        chat_id = (session.get("current_chat_id") or "").strip()

    # Use login-stored username from session, not passed again.
    name = session.get("username", "User").strip()
    client_name = str(credentials.get("client_name") or credentials.get("name") or "Auto-fill").strip()
    company = str(credentials.get("company") or "JorMall").strip()
    industry = str(credentials.get("industry") or "Auto-fill").strip()
    mobile = str(credentials.get("mobile") or "N/A").strip()

    credentials = {
        "client_name": client_name,
        "company": company,
        "industry": industry,
        "mobile": mobile,
        "name": name,
    }

    # Always refresh session info from credentials.
    session["user_name"] = name
    session["client_name"] = client_name
    session["company"] = company

    chat_doc = _load_or_create_chat(chat_id, name, credentials)
    chat_doc.update({
        "user": name,
        "name": name,
        "client_name": client_name,
        "company": company,
        "industry": industry,
        "mobile": mobile,
    })

    attachments = _read_uploaded_attachments(uploaded_files, relative_paths, chat_doc)
    if not user_msg and attachments:
        user_msg = "Please review the attached file(s)."
    if not user_msg:
        return jsonify({"reply": "No message received."}), 400

    # Store uploaded attachment information inside the same chat JSON.
    if attachments:
        chat_doc.setdefault("attachments", []).extend(attachments)

    # --- RAG: Retrieve top 20 relevant document chunks ---
    try:
        user_embedding = embed_text(user_msg)
        SIMILARITY_THRESHOLD = 0.75
        TOP_K = RAG_TOP_K
        ranked = []
        for record in iter_embedded_records():
            chunk = record.get("chunk", "")
            emb = record.get("embedding")
            similarity = cosine_similarity(user_embedding, emb)
            ranked.append((chunk, similarity, record))
        ranked.sort(key=lambda x: (-x[1], x[0]))
        filtered_chunks = [chunk for chunk, sim, _record in ranked if sim >= SIMILARITY_THRESHOLD]
        if len(filtered_chunks) < TOP_K:
            additional_chunks = [chunk for chunk, _sim, _record in ranked if chunk not in filtered_chunks]
            filtered_chunks += additional_chunks[:TOP_K - len(filtered_chunks)]
        top_chunks = filtered_chunks[:TOP_K]
        context = "\n\n".join(top_chunks) if top_chunks else "No relevant data found."
    except Exception as e:
        print("Embedding or similarity error:", e)
        return jsonify({"reply": "An error occurred during context retrieval."}), 500

    client_profile = f"Name: {name}, Company: {company}, Industry: {industry}"
    current_attachment_context = _attachment_context(attachments) if attachments else "No new attachments in this prompt."
    all_attachment_context = _attachment_context(chat_doc.get("attachments", [])) if chat_doc.get("attachments") else "No attachments stored in this chat yet."

    user_prompt = f"""
[Client profile: {client_profile}]

[Knowledge base context:]
{context}

[Attachments added with this prompt:]
{current_attachment_context}

[All attachment information already saved in this chat JSON:]
{all_attachment_context}

[User question:]
{user_msg}
""".strip()

    messages = _build_chat_messages(chat_doc, user_prompt)

    try:
        chat_response = get_openai_client().chat.completions.create(
            model="gpt-5.5",
            messages=messages
        )
        reply = chat_response.choices[0].message.content.strip()

        timestamp = _now_iso()
        user_entry = {
            "role": "user",
            "user_message": user_msg,
            "content": user_msg,
            "attachments": attachments,
            "timestamp": timestamp
        }
        assistant_entry = {
            "role": "assistant",
            "bot_reply": reply,
            "content": reply,
            "timestamp": _now_iso()
        }
        chat_doc.setdefault("messages", []).append(user_entry)
        chat_doc.setdefault("messages", []).append(assistant_entry)
        _save_chat(chat_doc)
        session["current_chat_id"] = chat_doc.get("chat_id")

        return jsonify({
            "reply": reply,
            "chat_id": chat_doc.get("chat_id"),
            "filename": chat_doc.get("filename"),
            "chat_filename": chat_doc.get("filename"),
            "title": _sidebar_chat_title(chat_doc, is_current=True),
            "has_attachments": chat_doc.get("has_attachments", False),
            "attachment_count": chat_doc.get("attachment_count", len(chat_doc.get("attachments", []))),
            "attachments": attachments
        })

    except Exception as e:
        print("OpenAI error:", e)
        # Save the user's prompt and attachment metadata even if the model call fails.
        chat_doc.setdefault("messages", []).append({
            "role": "user",
            "user_message": user_msg,
            "content": user_msg,
            "attachments": attachments,
            "timestamp": _now_iso(),
            "status": "model_error"
        })
        _save_chat(chat_doc)
        session["current_chat_id"] = chat_doc.get("chat_id")
        return jsonify({"reply": "An error occurred, please try again later.", "chat_id": chat_doc.get("chat_id"), "filename": chat_doc.get("filename"), "chat_filename": chat_doc.get("filename"), "title": _sidebar_chat_title(chat_doc, is_current=True)}), 500


## ---- Documents Content Serving ---- 
import mammoth

def read_docx(file_path):
    with open(file_path, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file)
        html = result.value  # The clean HTML content
        messages = result.messages  # Any conversion messages (warnings)

    return html  # Already safe to inject into chat if using `marked.parse()` or direct HTML




@app.route('/get-docx-content')
@login_required
def get_docx_content():
    filename = os.path.basename(request.args.get('file') or "")
    if not filename or not filename.endswith('.docx'):
        return jsonify({'reply': "⚠️ Invalid or missing file name."}), 400

    filepath = os.path.join(DOCUMENTS_FOLDER, filename)

    if not os.path.isfile(filepath):
        return jsonify({'reply': f"⚠️ File '{filename}' not found."}), 404

    try:
        print(f"📄 Reading file: {filepath}")
        content = read_docx(filepath)
        return jsonify({'reply': content})
    except Exception as e:
        print(f"❌ Error reading .docx file: {e}")
        return jsonify({'reply': f"⚠️ Error reading document: {str(e)}"}), 500



# --- Bitly API Generation ----

def _slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:80] if s else "na"

def _now_amman():
    return datetime.now(ZoneInfo("Asia/Amman"))

@app.route("/bitly-shorten", methods=["POST"])
@login_required
def bitly_shorten():
    data = request.get_json(silent=True) or {}
    long_url = data.get("long_url")
    # Optional metadata you might pass from the UI
    label = data.get("label")
    sms_type = data.get("smsType")
    company_name = data.get("companyName")  # <- from modal
    created_by = session.get("user") or data.get("created_by") or "unknown"
    if not long_url:
        return jsonify({"error": "Missing URL"}), 400

    headers = {
        "Authorization": f"Bearer {BITLY_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"long_url": long_url}

    res = requests.post("https://api-ssl.bitly.com/v4/shorten", json=payload, headers=headers)
    if res.status_code != 200:
        # Log the failure as well so you can diagnose later
        ts = _now_amman().isoformat(timespec="seconds")
        fail_entry = {
            "timestamp_iso": ts,
            "long_url": long_url,
            "status_code": res.status_code,
            "error_body": res.text,
            "created_by": created_by,
            "label": label,
            "company_name":company_name,
            "sms_type": sms_type,
        }
        # best-effort failure log
        try:
            with open(os.path.join(BITLY_LOG_DIR, f"{ts.replace(':','-')}_ERROR.json"), "w", encoding="utf-8") as f:
                json.dump(fail_entry, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return jsonify({"error": "Bitly API failed"}), 502

    body = res.json()
    short_url = body.get("link")               # e.g., https://bit.ly/xxxx
    bitly_id = body.get("id")                  # e.g., bit.ly/xxxx
    ts = _now_amman()
    ts_iso = ts.isoformat(timespec="seconds")
    ts_for_filename = ts_iso.replace(":", "-")

    # file name: 2025-08-10T12-34-56_bit.ly-xxxx.json
    base_id = _slugify(bitly_id or short_url or "bitly")
    filename = f"{ts_for_filename}_{base_id}.json"
    path = os.path.join(BITLY_LOG_DIR, filename)

    log_entry = {
        "timestamp_iso": ts_iso,
        "timestamp_tz": "Asia/Amman",
        "long_url": long_url,
        "short_url": short_url,
        "bitly_id": bitly_id,            # useful for Bitly API follow-ups
        "bitly_response": body,          # keep full body for auditing
        "created_by": created_by,
        "company_name":company_name,
        "label": label,
        "sms_type": sms_type,
        "user_agent": request.headers.get("User-Agent"),
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, ensure_ascii=False, indent=2)

    # Return a reference you can store in your UI/session
    ref_id = filename[:-5]  # strip .json
    return jsonify({
        "short_url": short_url,
        "ref_id": ref_id,           # <-- use this later to fetch/attach
        "created_at": ts_iso
    })

@app.route("/bitly-logs", methods=["GET"])
@login_required
def list_bitly_logs():
    # ?limit=50 (optional)
    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        limit = 100
    files = sorted(
        (f for f in os.listdir(BITLY_LOG_DIR) if f.endswith(".json")),
        reverse=True
    )
    files = files[:limit]
    return jsonify({"items": files})

@app.route("/bitly-logs/<ref_id>", methods=["GET"])
@login_required
def get_bitly_log(ref_id):
    # ref_id is filename without .json
    safe = _slugify(ref_id)
    path = os.path.join(BITLY_LOG_DIR, safe + ".json")
    if not os.path.isfile(path):
        abort(404, description="Log not found")
    with open(path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

# ---- Emails Logic ----

def is_valid_email(email):
    return re.match(r"^[^@]+@[^@]+\.[^@]+$", email)

@app.route("/send-email", methods=["POST"])
@login_required
def send_email():
    data = request.json
    recipient = data.get("to", "").strip()
    cc = data.get("cc", "").strip()
    body = data.get('body') or data.get('message')
    print(body)
    if not recipient or not body:
        return jsonify({"message": "Missing recipient or body."}), 400

    if not is_valid_email(recipient):
        return jsonify({"message": "Invalid recipient email."}), 400

    if not DEFAULT_SENDER_EMAIL or not SMTP_PASSWORD:
        return jsonify({"message": "Server email configuration missing."}), 500

    try:
        msg = EmailMessage()
        msg["Subject"] = "Chat Transcript from JorMall Assistant"
        msg["From"] = DEFAULT_SENDER_EMAIL
        msg["To"] = recipient

        if cc:
            msg["Cc"] = cc

        # Set both plain text and HTML parts
        msg.set_content("This email contains an HTML version of your chat transcript.")
        msg.add_alternative(body, subtype='html')

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        log_admin_activity(
        username=session.get("username", "unknown"),
        action="email_sent",
        to=recipient,
        subject="Full Chat from JorMall Assistant"
        )
        return jsonify({"message": "Email sent successfully."})

    except Exception as e:
        print("Email error:", e)
        return jsonify({"message": f"Error sending email: {e}"}), 500

@app.route('/send-email-with-attachment', methods=['POST'])
@login_required
def send_email_with_attachment():
    data = request.json
    print("DEBUG POST DATA:", data)  # 👈 add this log
    recipient_email = data.get('to')
    cc_email = data.get('cc', '')
    message_html = data.get('message', '')
    filename = os.path.basename(data.get('filename') or "")

    if not recipient_email or not filename or not message_html:
        return jsonify({"error": "Missing required fields"}), 400


    file_path = os.path.join('documents', filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    msg = EmailMessage()
    msg['Subject'] = 'Chat Message + Attachment from JorMall Assistant'
    msg['From'] = DEFAULT_SENDER_EMAIL
    msg['To'] = recipient_email

    if cc_email and is_valid_email(cc_email):
        msg['Cc'] = cc_email

    msg.set_content("This email contains a formatted chat reply and an attached document.")
    msg.add_alternative(message_html, subtype='html')

    with open(file_path, 'rb') as f:
        file_data = f.read()
        file_name = os.path.basename(file_path)
        msg.add_attachment(file_data, maintype='application',
                           subtype='vnd.openxmlformats-officedocument.wordprocessingml.document',
                           filename=file_name)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
        log_admin_activity(
        username=session.get("username", "unknown"),
        action="email_with_attachment",
        to=recipient_email,
        filename=filename,
        subject="Chat Message + Attachment"
        )
        return jsonify({"success": True})
    except Exception as e:
        print("Email error:", e)
        return jsonify({"error": str(e)}), 500



# ---- Chat history by user ----
LOGS_DIR = CHAT_LOGS_DIR

@app.route('/history/list')
@login_required
def list_chat_logs():
    # If no user is supplied, list all local chat JSON files. This keeps Previous Chats visible
    # when the app is used locally without the old login/session flow.
    user = str(session.get('username') or '').strip()

    current_chat_id = (request.args.get("current_chat_id") or session.get("current_chat_id") or "").strip()

    results = []
    if not os.path.isdir(LOGS_DIR):
        return jsonify(results)

    for filename in os.listdir(LOGS_DIR):
        if not filename.endswith('.json'):
            continue
        path = os.path.join(LOGS_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue

        # New chat JSON files store the username inside the file.
        is_new_chat = isinstance(payload, dict) and payload.get("version") == 2
        if is_new_chat:
            file_user = payload.get("user") or payload.get("name")
            if user and file_user != user:
                continue
            created = payload.get("created_at") or payload.get("updated_at") or ""
            updated = payload.get("updated_at") or created
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00")) + timedelta(hours=3)
                formatted_dt = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                formatted_dt = updated[:16]
            has_attachments = bool(payload.get("has_attachments")) or any(
                isinstance(m, dict) and m.get("attachments") for m in payload.get("messages", [])
            )
            item_chat_id = payload.get("chat_id") or filename[:-5]
            is_current = bool(current_chat_id and current_chat_id == item_chat_id)
            results.append({
                "filename": filename,
                "chat_id": item_chat_id,
                "user": file_user,
                "datetime": formatted_dt,
                "event": payload.get("event", "chat"),
                "mobile": payload.get("mobile"),
                "name": payload.get("name"),
                "client_name": payload.get("client_name"),
                "company": payload.get("company"),
                "industry": payload.get("industry"),
                "title": _sidebar_chat_title(payload, is_current=is_current),
                "has_attachments": has_attachments,
                "attachment_count": payload.get("attachment_count", len(payload.get("attachments", [])))
            })
            continue

        # Backwards compatibility with old chat logs named like: user_client_company_timestamp.json
        name_wo_ext = filename[:-5]
        parts = name_wo_ext.split("_")
        if user and (not parts or parts[0] != user):
            continue
        try:
            timestamp_str = parts[-1]
            dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H-%M-%S") + timedelta(hours=3)
            formatted_dt = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            formatted_dt = ""

        def get_fields(obj):
            return {
                "event": obj.get("event"),
                "mobile": obj.get("mobile"),
                "name": obj.get("name"),
                "client_name": obj.get("client_name"),
                "company": obj.get("company"),
                "industry": obj.get("industry"),
            }

        fields = None
        if isinstance(payload, dict):
            fields = get_fields(payload)
        elif isinstance(payload, list):
            for item in reversed(payload):
                if isinstance(item, dict) and (item.get("event") == "chat" or any(k in item for k in ("client_name", "company", "industry", "mobile", "name"))):
                    fields = get_fields(item)
                    break
        if fields is None:
            fields = {k: None for k in ["event", "mobile", "name", "client_name", "company", "industry"]}

        old_messages = payload.get("messages", []) if isinstance(payload, dict) else []
        has_attachments = any(isinstance(m, dict) and m.get("attachments") for m in old_messages)
        first_msg = ""
        for m in old_messages:
            if isinstance(m, dict) and m.get("user_message"):
                first_msg = m.get("user_message", "")[:55]
                break

        item_chat_id = filename[:-5]
        is_current = bool(current_chat_id and current_chat_id == item_chat_id)
        legacy_title_payload = {**fields, "user": user}
        results.append({
            "filename": filename,
            "chat_id": item_chat_id,
            "user": user,
            "datetime": formatted_dt,
            "event": fields["event"],
            "mobile": fields["mobile"],
            "name": fields["name"],
            "client_name": fields["client_name"],
            "company": fields["company"],
            "industry": fields["industry"],
            "title": _sidebar_chat_title(legacy_title_payload, is_current=is_current),
            "has_attachments": has_attachments,
            "attachment_count": 0
        })

    results.sort(key=lambda x: x.get("datetime") or "", reverse=True)
    return jsonify(results)

@app.route('/history/load/<path:filename>')
@login_required
def load_chat(filename):
    safe_name = os.path.basename(filename)
    if not safe_name.endswith('.json'):
        safe_name += '.json'
    filepath = os.path.join(LOGS_DIR, safe_name)
    if not os.path.exists(filepath):
        abort(404)
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        file_user = str(data.get("user") or data.get("name") or "")
        if file_user and file_user != str(session.get("username") or ""):
            abort(404)
        data.setdefault("chat_id", safe_name[:-5])
        data.setdefault("filename", safe_name)
        data.setdefault("messages", [])
        data.setdefault("attachments", [])
        data.setdefault("attachment_count", _count_attachments_in_chat(data))
        data.setdefault("has_attachments", any(isinstance(m, dict) and m.get("attachments") for m in data.get("messages", [])) or data.get("attachment_count", 0) > 0)
        _normalize_chat_attachments(data)
        session["current_chat_id"] = data.get("chat_id")
        data["title"] = _sidebar_chat_title(data, is_current=True)
        return jsonify(data)
    return jsonify({
        "chat_id": safe_name[:-5],
        "filename": safe_name,
        "title": "Current Chat",
        "messages": data if isinstance(data, list) else [],
        "attachments": [],
        "has_attachments": False
    })

@app.route("/admin/activity-log")
@admin_required
def serve_activity_log_html():
    return send_from_directory("static/admin", "activity_log.html")
@app.route("/admin/activity-log-data")
@admin_required
def get_activity_log_data():
    log_file = "logs/activity_log.jsonl"
    entries = []

    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

    entries = sorted(entries, key=lambda x: x["timestamp"], reverse=True)
    return jsonify(entries)


@app.route("/admin/users", strict_slashes=False)
@admin_required
def serve_user_management_html():
    return send_from_directory("static/admin", "user_management.html")


@app.route("/admin/api/users", methods=["GET"])
@admin_required
def admin_list_users():
    data, status = user_directory_request("/users", "GET")
    return jsonify(data), status


@app.route("/admin/api/users", methods=["POST"])
@admin_required
def admin_create_user():
    payload = request.get_json(silent=True) or {}
    payload = {
        "username": payload.get("username"),
        "email": payload.get("email"),
        "password": payload.get("password"),
        "role": payload.get("role", "user"),
        "categories": payload.get("categories", ["General"]),
        "actor": session.get("username") or "admin",
    }
    data, status = user_directory_request("/users", "POST", payload)
    return jsonify(data), status


@app.route("/admin/api/users/<int:user_id>", methods=["PATCH"])
@admin_required
def admin_update_user(user_id):
    incoming = request.get_json(silent=True) or {}
    payload = {
        key: incoming[key]
        for key in ("email", "role", "active", "categories")
        if key in incoming
    }
    payload["actor"] = session.get("username") or "admin"
    data, status = user_directory_request(f"/users/{user_id}", "PATCH", payload)
    return jsonify(data), status


@app.route("/admin/api/users/<int:user_id>/password", methods=["PATCH"])
@admin_required
def admin_change_user_password(user_id):
    incoming = request.get_json(silent=True) or {}
    password = str(incoming.get("password") or "")
    if len(password) < 8:
        return jsonify({
            "success": False,
            "error": "Password must be at least 8 characters.",
        }), 400
    payload = {
        "password": password,
        "actor": session.get("username") or "admin",
    }
    data, status = user_directory_request(f"/users/{user_id}", "PATCH", payload)
    if status == 200 and data.get("success"):
        data["session_refresh_required"] = int(session.get("user_id") or 0) == user_id
    return jsonify(data), status



def _normalize_document_language(value):
    """Return 'ar' or 'en' for the document language selected in the frontend."""
    value = (value or "").strip().lower()
    if value in {"ar", "arabic", "arabic document", "arabic_document", "arabic docx", "arabic_docx", "عربي", "العربية"}:
        return "ar"
    return "en"


def _normalize_campaign_analysis_file(json_path):
    """Normalize campaign JSON so document generation never indexes a string as an object.

    AI or legacy generators may occasionally save an analysis section as a plain string,
    list, or JSON-encoded string. Convert those variants to the canonical mapping used by
    both English and Arabic DOCX generators.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise TypeError("Campaign JSON root must be an object.")

    analysis = payload.get("analysis", {})
    if isinstance(analysis, str):
        stripped = analysis.strip()
        if stripped:
            try:
                decoded = json.loads(stripped)
                analysis = decoded
            except (json.JSONDecodeError, TypeError):
                analysis = {"Campaign Analysis": {"header": "Campaign Analysis", "answer": stripped}}
        else:
            analysis = {}

    if isinstance(analysis, list):
        converted = {}
        for index, item in enumerate(analysis, start=1):
            if isinstance(item, dict):
                header = str(item.get("header") or item.get("title") or f"Section {index}")
                converted[header] = item
            else:
                header = f"Section {index}"
                converted[header] = {"header": header, "answer": str(item or "")}
        analysis = converted

    if not isinstance(analysis, dict):
        analysis = {"Campaign Analysis": {"header": "Campaign Analysis", "answer": str(analysis or "")}}

    normalized = {}
    for key, content in analysis.items():
        key_text = str(key or "Campaign Analysis")
        if isinstance(content, str):
            content = {"header": key_text, "answer": content}
        elif not isinstance(content, dict):
            content = {"header": key_text, "answer": str(content or "")}
        else:
            content = dict(content)
            content.setdefault("header", key_text)
            content["answer"] = str(content.get("answer") or "")
        normalized[key_text] = content

    # Canonicalize Chain SMS data for both DOCX generators.
    # Legacy/current generators can store chain_messages as plain pitch strings while
    # the document summary expects objects containing pitch/date/time. Merge the
    # separate date/time arrays into each message and preserve already-structured data.
    raw_chain_messages = payload.get("chain_messages", []) or []
    raw_chain_dates = payload.get("chain_delivery_dates", []) or []
    raw_chain_times = payload.get("chain_delivery_times", []) or []

    if isinstance(raw_chain_messages, str):
        stripped = raw_chain_messages.strip()
        if stripped:
            try:
                decoded = json.loads(stripped)
                raw_chain_messages = decoded if isinstance(decoded, list) else [decoded]
            except (json.JSONDecodeError, TypeError):
                raw_chain_messages = [stripped]
        else:
            raw_chain_messages = []
    elif not isinstance(raw_chain_messages, list):
        raw_chain_messages = [raw_chain_messages]

    if not isinstance(raw_chain_dates, list):
        raw_chain_dates = [raw_chain_dates] if raw_chain_dates else []
    if not isinstance(raw_chain_times, list):
        raw_chain_times = [raw_chain_times] if raw_chain_times else []

    canonical_chain_messages = []
    for index, item in enumerate(raw_chain_messages):
        fallback_date = str(raw_chain_dates[index] or "").strip() if index < len(raw_chain_dates) else ""
        fallback_time = str(raw_chain_times[index] or "").strip() if index < len(raw_chain_times) else ""
        if isinstance(item, dict):
            pitch = item.get("pitch") or item.get("message") or item.get("text") or ""
            date = item.get("date") or item.get("delivery_date") or fallback_date
            time = item.get("time") or item.get("delivery_time") or fallback_time
            canonical = dict(item)
            canonical["pitch"] = str(pitch or "").strip()
            canonical["date"] = str(date or "").strip()
            canonical["time"] = str(time or "").strip()
        else:
            canonical = {
                "pitch": str(item or "").strip(),
                "date": fallback_date,
                "time": fallback_time,
            }
        if canonical["pitch"] or canonical["date"] or canonical["time"]:
            canonical_chain_messages.append(canonical)

    payload["chain_messages"] = canonical_chain_messages
    # Keep the arrays synchronized for compatibility with older code paths.
    payload["chain_delivery_dates"] = [msg.get("date", "") for msg in canonical_chain_messages]
    payload["chain_delivery_times"] = [msg.get("time", "") for msg in canonical_chain_messages]

    payload["analysis"] = normalized
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)
    return json_path

# ---- Generating Campaigns and Messages ----
@app.route("/api/generate-campaign", methods=["POST"])
@login_required
def generate_campaign():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request format. Expected a JSON object."}), 400

    stage = "validating campaign request"

    # Mandatory fields
    sms_type = (data.get("smsType") or "smart").strip()
    company_name = (data.get("companyName") or "").strip()
    company_url = (data.get("companyURL") or "").strip()
    campaign_brief = (data.get("campaignBrief") or "").strip()

    # Optional fields (safe strip)
    bitly_link = (data.get("bitlyLink") or "").strip()
    phone_number = (data.get("phoneNumber") or "").strip()
    cities = (data.get("cities") or "").strip()
    amman_direction = (data.get("ammanDirection") or "").strip()
    delivery_date = (data.get("deliveryDate") or "").strip()
    document_language = _normalize_document_language(
        data.get("documentLanguage") or data.get("outputLanguage") or data.get("language") or "en"
    )
    requested_languages = data.get("documentLanguages") or [document_language]
    if isinstance(requested_languages, str):
        requested_languages = [requested_languages]
    requested_languages = [_normalize_document_language(x) for x in requested_languages]
    requested_languages = [x for x in requested_languages if x in {"en", "ar"}]
    if not requested_languages:
        requested_languages = ["en"]
    # Generate campaign content once in English, then translate that exact JSON for Arabic.
    # This prevents the English and Arabic DOCX files from having different ideas/recommendations.
    generation_language = "en"

    # Handle chain messages if smsType is 'chain'.
    # Frontend sends objects like: {"pitch": "...", "date": "...", "time": "..."}.
    # Backend campaign generator expects a clean list of pitch strings plus separate date/time lists.
    raw_chain_messages = data.get("chainMessages", []) or []
    chain_messages = []
    chain_delivery_dates = []
    chain_delivery_times = []
    for item in raw_chain_messages:
        if isinstance(item, dict):
            pitch = (item.get("pitch") or item.get("message") or item.get("text") or "").strip()
            date = (item.get("date") or "").strip()
            time = (item.get("time") or "").strip()
        else:
            pitch = str(item or "").strip()
            date = ""
            time = ""
        if pitch:
            chain_messages.append(pitch)
            chain_delivery_dates.append(date)
            chain_delivery_times.append(time)
    chain_campaign_title = (data.get("chainCampaignTitle") or "").strip()
    if sms_type == "chain" and not campaign_brief:
        campaign_brief = chain_campaign_title or " | ".join(chain_messages)
    
    optin_sms_notes = (data.get("optinSMSNotes") or ""). strip() 
    optin_bitly_link = (data.get("optinBitlyLink") or ""). strip()
    optin_phone_number = (data.get("optinPhoneNumber") or ""). strip()
    # Check for missing required fields
    if not (company_name and company_url):
        if company_name:
            safe_company_name = _sanitize_activity_text(company_name, 160)
            campaign_label = _campaign_activity_label(sms_type)
            log_admin_activity(
                username=session.get("username", "unknown"),
                action=f"generate campaign ({sms_type})",
                description=_company_activity_description(campaign_label, safe_company_name),
                event_key=f"create_campaign_{_safe_token(sms_type, 'sms').lower()}",
                company_name=safe_company_name,
                status="failed",
                stage="validating campaign request",
                error="Missing required fields (Company Name or URL).",
            )
        return jsonify({"error": "Missing required fields (Company Name or URL)."}), 400


    try:
        # Generate unique filename
        campaign_id = str(uuid4())
        json_path = os.path.join(JSON_DIR, f"{campaign_id}_analysis.json")

        # Check the SMS type and call the appropriate function
        stage = f"generating {sms_type} campaign content"
        if sms_type == "smart":
            # Generate Smart Reach Campaign
            run_smart_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                campaign_brief=campaign_brief,
                bitly_link=bitly_link,
                phone_number=phone_number,
                cities=cities,
                amman_direction=amman_direction,
                delivery_date=delivery_date,
                output_language=generation_language,
                document_language=generation_language
            )
        elif sms_type == "chain":
            # Generate Chain Campaign
            run_chain_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                chain_campaign_title=chain_campaign_title,
                company_url=company_url,
                campaign_brief=campaign_brief,
                chain_messages=chain_messages,  # Chain specific logic
                chain_delivery_dates=chain_delivery_dates,
                chain_delivery_times=chain_delivery_times,
                cities=cities,
                amman_direction=amman_direction,
                output_language=generation_language,
                document_language=generation_language
                )
        elif sms_type=="premium":
            run_premium_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                campaign_brief=campaign_brief,
                output_language=generation_language,
                document_language=generation_language
            )
        elif sms_type=="personalized":
            run_personalized_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                campaign_brief=campaign_brief,
                bitly_link=bitly_link,
                phone_number=phone_number,
                cities=cities,
                amman_direction=amman_direction,
                delivery_date=delivery_date,
                output_language=generation_language,
                document_language=generation_language
            )
       
        elif sms_type=="lead":
            run_lead_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                output_language=generation_language,
                document_language=generation_language
                )
        elif sms_type=="optin":
            run_optin_sms_campaign_generation(
                json_path=json_path,
                company_name=company_name,
                company_url=company_url,
                optin_sms_notes=optin_sms_notes,
                optin_bitly_link=optin_bitly_link,
                optin_phone_number=optin_phone_number,
                output_language=generation_language,
                document_language=generation_language
                )
        
        else:
            safe_company_name = _sanitize_activity_text(company_name, 160)
            log_admin_activity(
                username=session.get("username", "unknown"),
                action=f"generate campaign ({sms_type})",
                description=_company_activity_description("Create SMS Document", safe_company_name),
                event_key=f"create_campaign_{_safe_token(sms_type, 'sms').lower()}",
                company_name=safe_company_name,
                status="failed",
                stage="validating campaign type",
                error="Invalid SMS type.",
            )
            return jsonify({"error": "Invalid SMS type."}), 400

        # Normalize any legacy or AI-returned string/list analysis shapes before DOCX creation.
        stage = "normalizing generated campaign data"
        _normalize_campaign_analysis_file(json_path)

        # Generate requested DOCX files from the same canonical English JSON.
        generated_files = {}
        first_filename = None

        if "en" in requested_languages:
            stage = "creating the English Word document"
            filename_en = generate_ai_docx(campaign_id, json_path)
            generated_files["en"] = public_path(f"/exports/docx/{os.path.basename(filename_en)}")
            first_filename = first_filename or filename_en

        if "ar" in requested_languages:
            stage = "translating campaign content to Arabic"
            arabic_json_path = translate_campaign_json_to_arabic(json_path)
            _normalize_campaign_analysis_file(arabic_json_path)
            stage = "creating the Arabic Word document"
            filename_ar = generate_arabic_ai_docx(campaign_id, arabic_json_path, language="ar")
            generated_files["ar"] = public_path(f"/exports/docx/{os.path.basename(filename_ar)}")
            first_filename = first_filename or filename_ar

        if not generated_files:
            filename_en = generate_ai_docx(campaign_id, json_path)
            generated_files["en"] = public_path(f"/exports/docx/{os.path.basename(filename_en)}")
            first_filename = filename_en

        primary_url = generated_files.get(requested_languages[0]) or next(iter(generated_files.values()))
        campaign_label = _campaign_activity_label(sms_type)
        safe_company_name = _sanitize_activity_text(company_name, 160)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate campaign ({sms_type})",
            description=_company_activity_description(campaign_label, safe_company_name),
            event_key=f"create_campaign_{_safe_token(sms_type, 'sms').lower()}",
            company_name=safe_company_name,
            status="success",
            filename=os.path.basename(first_filename or ""),
        )
        return jsonify({"manualDocxUrl": primary_url, "manualDocxUrls": generated_files})

    except Exception as e:
        print(f"❌ Campaign generation error during {stage}: {e}")
        traceback.print_exc()
        safe_company_name = _sanitize_activity_text(company_name, 160)
        campaign_label = _campaign_activity_label(sms_type)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate campaign ({sms_type})",
            description=_company_activity_description(campaign_label, safe_company_name),
            event_key=f"create_campaign_{_safe_token(sms_type, 'sms').lower()}",
            company_name=safe_company_name,
            status="failed",
            stage=_sanitize_activity_text(stage, 160),
            error=str(e),
        )
        return jsonify({"error": f"Failed to generate campaign during {stage}: {str(e)}"}), 500


# ------------------ Profile Generation ------------------
@app.route("/api/generate-profile", methods=["POST"])
@login_required
def generate_profile():
    data = request.get_json(silent=True) or {}

    company_name = str(data.get("companyName", "")).strip()
    company_url = str(data.get("companyURL", "")).strip()
    company_about = str(data.get("companyAbout", "")).strip()
    document_language = _normalize_document_language(
        data.get("documentLanguage") or data.get("reportLanguage") or "en"
    )
    report_language = "Arabic" if document_language == "ar" else "English"

    if not company_name:
        return jsonify({"error": "Company name is required"}), 400
    if not company_url and not company_about:
        safe_company_name = _sanitize_activity_text(company_name, 160)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} profile for {safe_company_name}",
            description=_company_activity_description("Generate Client Profile Report", safe_company_name),
            event_key="generate_client_profile_report",
            company_name=safe_company_name,
            document_language=document_language,
            status="failed",
            stage="validating profile request",
            error="Missing company URL or company description text.",
        )
        return jsonify({"error": "Please provide either a company URL or company description text"}), 400

    try:
        profile_id = str(uuid4())
        json_path = os.path.join(JSON_DIR, f"{profile_id}_analysis.json")

        run_profile_analysis_generation(
            company_name=company_name,
            report_language=report_language,
            json_path=json_path,
            company_url=company_url or None,
            company_about=company_about or None,
        )

        filename = (
            generate_arabic_ai_docx(profile_id, json_path, language="ar")
            if document_language == "ar"
            else generate_ai_docx(profile_id, json_path)
        )
        docx_url = public_path(f"/exports/docx/{os.path.basename(filename)}")

        safe_company_name = _sanitize_activity_text(company_name, 160)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} profile for {safe_company_name}",
            description=_company_activity_description("Generate Client Profile Report", safe_company_name),
            event_key="generate_client_profile_report",
            company_name=safe_company_name,
            document_language=document_language,
            status="success",
            filename=os.path.basename(filename),
        )

        return jsonify({"manualDocxUrl": docx_url, "documentLanguage": document_language})

    except Exception as e:
        print("❌ Profile generation error:", e)
        traceback.print_exc()
        safe_company_name = _sanitize_activity_text(company_name, 160)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} profile for {safe_company_name}",
            description=_company_activity_description("Generate Client Profile Report", safe_company_name),
            event_key="generate_client_profile_report",
            company_name=safe_company_name,
            document_language=document_language,
            status="failed",
            error=str(e),
        )
        return jsonify({"error": f"Failed to generate profile: {str(e)}"}), 500



# ------------------ Marketing Plan Generation ------------------
@app.route("/api/generate-marketing-plan", methods=["POST"])
@login_required
def generate_marketing_plan():
    data = request.get_json(silent=True) or {}

    company_name = str(data.get("companyName", "")).strip()
    company_url = str(data.get("companyURL", "")).strip()
    company_about = str(data.get("companyAbout", "")).strip()
    document_language = _normalize_document_language(
        data.get("documentLanguage") or data.get("reportLanguage") or "en"
    )
    report_language = "Arabic" if document_language == "ar" else "English"

    if not company_name:
        return jsonify({"error": "Company name is required"}), 400
    if not company_url and not company_about:
        safe_company_name = _sanitize_activity_text(company_name, 160)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} marketing plan for {safe_company_name}",
            description=_company_activity_description("Generate Marketing Plan", safe_company_name),
            event_key="generate_marketing_plan",
            company_name=safe_company_name,
            document_language=document_language,
            status="failed",
            stage="validating marketing plan request",
            error="Missing company URL or company description text.",
        )
        return jsonify({"error": "Please provide either a company URL or description text"}), 400

    try:
        plan_id = str(uuid4())
        json_path = os.path.join(JSON_DIR, f"{plan_id}_analysis.json")

        run_marketing_plan_generation(
            company_name=company_name,
            report_language=report_language,
            json_path=json_path,
            company_url=company_url or None,
            company_about=company_about or None,
        )

        filename = (
            generate_arabic_ai_docx(plan_id, json_path, language="ar")
            if document_language == "ar"
            else generate_ai_docx(plan_id, json_path)
        )
        docx_url = public_path(f"/exports/docx/{os.path.basename(filename)}")

        safe_company_name = _sanitize_activity_text(company_name, 160)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} marketing plan for {safe_company_name}",
            description=_company_activity_description("Generate Marketing Plan", safe_company_name),
            event_key="generate_marketing_plan",
            company_name=safe_company_name,
            document_language=document_language,
            status="success",
            filename=os.path.basename(filename),
        )

        return jsonify({"manualDocxUrl": docx_url, "documentLanguage": document_language})

    except Exception as e:
        print("❌ Marketing plan generation error:", e)
        traceback.print_exc()
        safe_company_name = _sanitize_activity_text(company_name, 160)
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} marketing plan for {safe_company_name}",
            description=_company_activity_description("Generate Marketing Plan", safe_company_name),
            event_key="generate_marketing_plan",
            company_name=safe_company_name,
            document_language=document_language,
            status="failed",
            error=str(e),
        )
        return jsonify({"error": f"Failed to generate marketing plan: {str(e)}"}), 500


# ------------------ Platform Benefits Generation ------------------
@app.route("/api/generate-platform-benefits", methods=["POST"])
@login_required
def generate_platform_benefits():
    data = request.get_json(silent=True) or {}

    company_name = str(data.get("companyName", "")).strip()
    company_url = str(data.get("companyURL", "")).strip()
    company_about = str(data.get("companyAbout", "")).strip()
    industry = str(data.get("industry", "")).strip()
    document_language = _normalize_document_language(
        data.get("documentLanguage") or data.get("reportLanguage") or "en"
    )
    report_language = "Arabic" if document_language == "ar" else "English"

    if not company_name:
        return jsonify({"error": "Company name is required"}), 400
    if not industry:
        return jsonify({"error": "Company industry is required for Platform Benefits"}), 400
    if industry not in PLATFORM_BENEFITS_INDUSTRIES:
        return jsonify({"error": "Please select a valid company industry"}), 400

    safe_company_name = _sanitize_activity_text(company_name, 160)
    try:
        report_id = str(uuid4())
        json_path = os.path.join(JSON_DIR, f"{report_id}_platform_benefits.json")

        run_platform_benefits_generation(
            company_name=company_name,
            industry=industry,
            report_language=report_language,
            json_path=json_path,
            company_url=company_url or None,
            company_about=company_about or None,
        )

        filename = (
            generate_arabic_ai_docx(report_id, json_path, language="ar")
            if document_language == "ar"
            else generate_ai_docx(report_id, json_path)
        )
        docx_url = public_path(f"/exports/docx/{os.path.basename(filename)}")

        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} platform benefits for {safe_company_name}",
            description=_company_activity_description("Generate Platform Benefits", safe_company_name),
            event_key="generate_platform_benefits",
            company_name=safe_company_name,
            document_language=document_language,
            status="success",
            filename=os.path.basename(filename),
            stage=_sanitize_activity_text(industry, 120),
        )

        return jsonify({
            "manualDocxUrl": docx_url,
            "documentLanguage": document_language,
            "industry": industry,
        })

    except Exception as e:
        print("❌ Platform Benefits generation error:", e)
        traceback.print_exc()
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} platform benefits for {safe_company_name}",
            description=_company_activity_description("Generate Platform Benefits", safe_company_name),
            event_key="generate_platform_benefits",
            company_name=safe_company_name,
            document_language=document_language,
            status="failed",
            error=str(e),
            stage=_sanitize_activity_text(industry, 120),
        )
        return jsonify({"error": f"Failed to generate Platform Benefits: {str(e)}"}), 500


# ------------------ AI Products Document Generation ------------------
@app.route("/api/generate-ai-product", methods=["POST"])
@login_required
def generate_ai_product_document():
    data = request.get_json(silent=True) or {}

    company_name = str(data.get("companyName", "")).strip()
    company_url = str(data.get("companyURL", "")).strip()
    company_about = str(data.get("companyAbout", "")).strip()
    product_type = str(data.get("productType", "")).strip()
    document_language = _normalize_document_language(
        data.get("documentLanguage") or data.get("reportLanguage") or "en"
    )
    report_language = "Arabic" if document_language == "ar" else "English"

    if not company_name:
        return jsonify({"error": "Company name is required"}), 400
    if product_type not in AI_PRODUCTS:
        return jsonify({"error": "Please select a valid AI product"}), 400
    if not company_url and not company_about:
        return jsonify({"error": "Please provide either a company URL or description text"}), 400

    safe_company_name = _sanitize_activity_text(company_name, 160)
    try:
        report_id = str(uuid4())
        json_path = os.path.join(JSON_DIR, f"{report_id}_ai_product.json")

        run_ai_product_generation(
            company_name=company_name,
            product_type=product_type,
            report_language=report_language,
            json_path=json_path,
            company_url=company_url or None,
            company_about=company_about or None,
        )

        filename = (
            generate_arabic_ai_docx(report_id, json_path, language="ar")
            if document_language == "ar"
            else generate_ai_docx(report_id, json_path)
        )
        docx_url = public_path(f"/exports/docx/{os.path.basename(filename)}")
        product_label = AI_PRODUCTS[product_type]["ar" if document_language == "ar" else "en"]

        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} AI product document for {safe_company_name}",
            description=_company_activity_description(f"Generate {product_label}", safe_company_name),
            event_key="generate_ai_product_document",
            company_name=safe_company_name,
            document_language=document_language,
            status="success",
            filename=os.path.basename(filename),
            stage=_sanitize_activity_text(product_type, 80),
        )

        return jsonify({
            "manualDocxUrl": docx_url,
            "documentLanguage": document_language,
            "productType": product_type,
            "productName": product_label,
        })
    except Exception as e:
        print("❌ AI Products generation error:", e)
        traceback.print_exc()
        log_admin_activity(
            username=session.get("username", "unknown"),
            action=f"generate {document_language} AI product document for {safe_company_name}",
            description=_company_activity_description("Generate AI Product Document", safe_company_name),
            event_key="generate_ai_product_document",
            company_name=safe_company_name,
            document_language=document_language,
            status="failed",
            error=str(e),
            stage=_sanitize_activity_text(product_type, 80),
        )
        return jsonify({"error": f"Failed to generate AI product document: {str(e)}"}), 500


## ---- Word Documents Serving Download ---- 

@app.route("/exports/docx/<path:filename>")
@login_required
def download_docx(filename):
    response = send_from_directory(
        EXPORT_DIR,
        filename,
        as_attachment=True,
        download_name=os.path.basename(filename),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

# -------------------------------------------------------------------
# JorMall Assistant frontend
# -------------------------------------------------------------------
## --- Favicon Icon ----
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(BASE_DIR, 'assets/images'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )
def check_api_key():
    api_key = request.headers.get("X-API-Key")
    if api_key != os.getenv("JORMALL_API_KEY"):
        return jsonify({"error": "Unauthorized"}), 401
## --- Check JORMALL ASSISTANT API KEY ---
if __name__ == "__main__":
    port = int(os.getenv("PORT", "2000"))
    host = os.getenv("HOST", "127.0.0.1")

    print(f"Starting JorMall Assistant at http://{host}:{port}")

    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
    )
