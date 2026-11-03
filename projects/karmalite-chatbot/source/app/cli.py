"""
أوامر التشغيل من الطرفية:

    python -m app.cli init                 # إنشاء الجداول والإندكسات
    python -m app.cli ingest [path] [-f]   # فهرسة البيانات
    python -m app.cli chunks [path]        # معاينة التقسيم بدون رفع (تشخيص)
    python -m app.cli search "سؤال"        # اختبار الاسترجاع لحاله
    python -m app.cli ask "سؤال"           # سؤال واحد
    python -m app.cli chat                 # محادثة تفاعلية
    python -m app.cli leads                # عرض العملاء المحتملين
    python -m app.cli health
    python -m app.cli sms-status
    python -m app.cli sms-send [id]
    python -m app.cli sms-worker --once
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .chunking import chunk_markdown
from .config import get_settings
from .db import healthcheck, init_schema
from .engine import chat
from .ingest import ingest_path
from .memory import list_escalations, list_leads
from .josms import configuration_status as sms_configuration_status
from .notifications import send_notification, send_pending_notifications
from .retrieval import retrieve

console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else get_settings().log_level,
        format="%(levelname)-7s | %(name)s | %(message)s",
    )


def cmd_init(_: argparse.Namespace) -> None:
    init_schema()
    console.print("[green]✔ تم إنشاء السكيما[/green]")


def cmd_ingest(args: argparse.Namespace) -> None:
    for result in ingest_path(args.path, force=args.force):
        console.print(result)


def cmd_chunks(args: argparse.Namespace) -> None:
    from pathlib import Path

    settings = get_settings()
    text = Path(args.path).read_text(encoding="utf-8")
    chunks = chunk_markdown(
        text,
        source=args.path,
        max_chars=settings.chunk_max_chars,
        min_chars=settings.chunk_min_chars,
        overlap=settings.chunk_overlap_chars,
    )
    for i, chunk in enumerate(chunks, 1):
        console.print(
            Panel(
                chunk.content,
                title=f"[{i}] {chunk.chunk_type} · {chunk.token_count} tokens",
                subtitle=chunk.breadcrumb,
                border_style="cyan",
            )
        )
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.chunk_type] = counts.get(chunk.chunk_type, 0) + 1
    console.print(f"\n[bold]المجموع: {len(chunks)} شانك[/bold] {counts}")


def cmd_search(args: argparse.Namespace) -> None:
    hits = retrieve(args.query)
    if not hits:
        console.print("[yellow]ما في نتائج فوق العتبة[/yellow]")
        return
    table = Table(title=f"نتائج: {args.query}")
    table.add_column("#", width=3)
    table.add_column("cosine", width=8)
    table.add_column("rrf", width=8)
    table.add_column("النوع", width=10)
    table.add_column("المقطع", overflow="fold")
    for i, hit in enumerate(hits, 1):
        table.add_row(
            str(i),
            f"{hit.vector_score:.3f}",
            f"{hit.rrf_score:.4f}",
            hit.chunk_type,
            hit.content[:180].replace("\n", " · "),
        )
    console.print(table)


def _print_answer(result) -> None:
    console.print(Panel(result.answer, title="المساعد", border_style="green"))
    if result.tool_calls:
        for call in result.tool_calls:
            console.print(f"[magenta]⚙ {call['name']}[/magenta] → {call['result']}")
    sources = ", ".join(f"#{s.id} {s.breadcrumb}" for s in result.sources[:4])
    console.print(f"[dim]المصادر: {sources or 'لا يوجد'}[/dim]\n")


def cmd_ask(args: argparse.Namespace) -> None:
    _print_answer(chat(args.query, session_id=f"cli-{uuid.uuid4().hex[:8]}", channel="cli"))


def cmd_chat(args: argparse.Namespace) -> None:
    session_id = args.session or f"cli-{uuid.uuid4().hex[:8]}"
    console.print(
        Panel(
            "محادثة تجريبية مع مساعد كارماليت — اكتب 'خروج' أو 'exit' للإنهاء.",
            border_style="blue",
        )
    )
    while True:
        try:
            message = console.input("[bold cyan]أنت:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in {"exit", "quit", "خروج"}:
            break
        if not message:
            continue
        _print_answer(chat(message, session_id=session_id, channel="cli"))


def cmd_leads(_: argparse.Namespace) -> None:
    rows = list_leads()
    table = Table(title="العملاء المحتملون")
    for column in ("ID", "الاسم", "الهاتف", "الخدمة", "الحالة", "التاريخ"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["full_name"],
            row["phone"],
            row["service_interest"] or "-",
            row["status"],
            row["created_at"].strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)

    escalations = list_escalations()
    if escalations:
        console.print("\n[bold red]تصعيدات مفتوحة:[/bold red]")
        for row in escalations:
            console.print(f"  [{row['level']}] #{row['id']} — {row['reason']}")


def cmd_health(_: argparse.Namespace) -> None:
    console.print(healthcheck())


def cmd_sms_status(_: argparse.Namespace) -> None:
    """يعرض الجاهزية بدون طباعة أي بيانات اعتماد."""
    console.print(sms_configuration_status())


def cmd_sms_send(args: argparse.Namespace) -> None:
    result = send_notification(args.id)
    console.print(result or {"status": "nothing_to_send"})


def cmd_sms_worker(args: argparse.Namespace) -> None:
    """عامل صادر بسيط؛ شغّله كعملية مستقلة بجانب FastAPI."""
    while True:
        results = send_pending_notifications(limit=args.batch)
        if results:
            console.print(results)
        if args.once:
            return
        time.sleep(args.interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="karmalite", description="Karmalite RAG CLI")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("path", nargs="?", default="data")
    p_ingest.add_argument("-f", "--force", action="store_true")
    p_ingest.set_defaults(func=cmd_ingest)

    p_chunks = sub.add_parser("chunks")
    p_chunks.add_argument("path", nargs="?", default="data/karmalite_kb.md")
    p_chunks.set_defaults(func=cmd_chunks)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.set_defaults(func=cmd_search)

    p_ask = sub.add_parser("ask")
    p_ask.add_argument("query")
    p_ask.set_defaults(func=cmd_ask)

    p_chat = sub.add_parser("chat")
    p_chat.add_argument("--session", default=None)
    p_chat.set_defaults(func=cmd_chat)

    sub.add_parser("leads").set_defaults(func=cmd_leads)
    sub.add_parser("health").set_defaults(func=cmd_health)
    sub.add_parser("sms-status").set_defaults(func=cmd_sms_status)

    p_sms_send = sub.add_parser("sms-send")
    p_sms_send.add_argument("id", type=int, nargs="?", default=None)
    p_sms_send.set_defaults(func=cmd_sms_send)

    p_sms_worker = sub.add_parser("sms-worker")
    p_sms_worker.add_argument("--once", action="store_true")
    p_sms_worker.add_argument("--batch", type=int, default=20)
    p_sms_worker.add_argument("--interval", type=int, default=10)
    p_sms_worker.set_defaults(func=cmd_sms_worker)

    args = parser.parse_args(argv)

    try:
        _setup_logging(args.verbose)
    except Exception as exc:
        console.print(
            Panel(
                f"[red]الإعدادات ناقصة:[/red] {exc}\n\n"
                "تأكد إنك عملت نسخة من [bold].env.example[/bold] باسم [bold].env[/bold] "
                "وحطيت فيها OPENAI_API_KEY و DATABASE_URL.",
                title="خطأ بالإعدادات",
                border_style="red",
            )
        )
        return 1

    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
