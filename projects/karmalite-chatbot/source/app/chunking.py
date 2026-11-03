"""
تقسيم الشانكس (Structure-aware chunking).

الفكرة: ما بنقص النص كل X حرف بشكل أعمى — بنقصّه حسب بنية المستند:
  • كل صف بجدول الأسعار = شانك مستقل (سؤال عن سعر خدمة بيرجّع صف الخدمة بالضبط)
  • كل سؤال وجواب بقسم الأسئلة الشائعة = شانك مستقل
  • النصوص والقوائم = تُجمَّع تحت نفس العنوان لحد الحد الأقصى، مع تداخل بسيط
  • كل شانك بيحمل "breadcrumb" (مسار العناوين) بمتنه عشان الإمبيدنج يفهم السياق
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text_utils import build_search_text, count_tokens

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")   # الفاصل الحقيقي بين الأعمدة (مش \| الهاربة)
_FAQ_START = re.compile(r"^\*\*\s*(?:س|Q)\s*[:：]")
_SENTENCE_END = re.compile(r"(?<=[.!?؟।])\s+|\n")


@dataclass
class Chunk:
    content: str
    breadcrumb: str
    chunk_type: str = "prose"
    metadata: dict = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        return build_search_text(self.content)

    @property
    def token_count(self) -> int:
        return count_tokens(self.content)


@dataclass
class _Block:
    breadcrumb: str
    kind: str          # prose | table | faq
    lines: list[str]
    section: str


# ----------------------------------------------------------------------
# 1) تفكيك المستند لبلوكات حسب العناوين
# ----------------------------------------------------------------------
def _parse_blocks(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    stack: dict[int, str] = {}
    buffer: list[str] = []
    kind = "prose"

    def breadcrumb() -> str:
        # بنستثني عنوان المستند (H1) لأنه بيتكرر بكل شانك وبياكل توكنز بدون فائدة تمييزية
        path = [stack[k] for k in sorted(stack) if k > 1]
        return " > ".join(path) if path else stack.get(1, "")

    def section() -> str:
        return stack[max(stack)] if stack else ""

    def flush() -> None:
        nonlocal buffer, kind
        body = [ln for ln in buffer if ln.strip()]
        if body:
            blocks.append(_Block(breadcrumb(), kind, body, section()))
        buffer = []
        kind = "prose"

    for raw in text.splitlines():
        line = raw.rstrip()
        heading = _HEADING.match(line)

        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            stack = {k: v for k, v in stack.items() if k < level}
            stack[level] = title
            continue

        if _TABLE_ROW.match(line):
            if kind != "table":
                flush()
                kind = "table"
            buffer.append(line)
            continue

        if kind == "table":          # انتهى الجدول
            flush()

        if not line.strip():         # سطر فاضي = نهاية بلوك
            flush()
            continue

        if _FAQ_START.match(line.strip()):
            flush()
            kind = "faq"

        buffer.append(line)

    flush()
    return blocks


# ----------------------------------------------------------------------
# 2) تحويل البلوكات لشانكس
# ----------------------------------------------------------------------
def _table_cells(line: str) -> list[str]:
    """يقسم صف جدول على الفواصل الحقيقية فقط، ويفكّ هروب \\| داخل الخلايا."""
    inner = line.strip()
    inner = _UNESCAPED_PIPE.sub("\x00", inner).strip("\x00")
    return [cell.replace("\\|", "|").strip() for cell in inner.split("\x00")]


def _split_table(block: _Block) -> list[Chunk]:
    """كل صف بيانات = شانك، بصيغة «العمود: القيمة» عشان يكون مقروء للموديل."""
    rows = [
        _table_cells(ln) for ln in block.lines if not _TABLE_SEPARATOR.match(ln)
    ]
    if len(rows) < 2:
        return []

    headers = rows[0]
    chunks: list[Chunk] = []

    for row in rows[1:]:
        pairs = [
            f"{headers[i] if i < len(headers) else f'حقل {i + 1}'}: {cell}"
            for i, cell in enumerate(row)
            if cell and cell not in {"-", "—"}
        ]
        if not pairs:
            continue
        body = "\n".join(pairs)
        chunks.append(
            Chunk(
                content=f"القسم: {block.breadcrumb}\n{body}",
                breadcrumb=block.breadcrumb,
                chunk_type="table_row",
                metadata={"section": block.section, "entity": row[0] if row else ""},
            )
        )
    return chunks


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """قص نص طويل على حدود الجُمل مع تداخل حرفي بسيط للحفاظ على السياق."""
    if len(text) <= max_chars:
        return [text]

    sentences = [s.strip() for s in _SENTENCE_END.split(text) if s and s.strip()]
    parts: list[str] = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            parts.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail} {sentence}".strip()

    if current:
        parts.append(current)
    return parts


def chunk_markdown(
    text: str,
    *,
    source: str,
    max_chars: int = 900,
    min_chars: int = 180,
    overlap: int = 120,
) -> list[Chunk]:
    blocks = _parse_blocks(text)
    chunks: list[Chunk] = []

    pending: list[str] = []          # بلوكات صغيرة مؤجلة للدمج
    pending_crumb: str | None = None
    pending_section = ""

    def flush_pending() -> None:
        nonlocal pending, pending_crumb, pending_section
        if not pending:
            return
        body = "\n".join(pending)
        for part in _split_long_text(body, max_chars, overlap):
            chunks.append(
                Chunk(
                    content=f"القسم: {pending_crumb}\n{part}",
                    breadcrumb=pending_crumb or "",
                    chunk_type="prose",
                    metadata={"section": pending_section},
                )
            )
        pending = []
        pending_crumb = None

    for block in blocks:
        if block.kind == "table":
            flush_pending()
            chunks.extend(_split_table(block))
            continue

        if block.kind == "faq":
            flush_pending()
            body = "\n".join(block.lines)
            chunks.append(
                Chunk(
                    content=f"القسم: {block.breadcrumb}\n{body}",
                    breadcrumb=block.breadcrumb,
                    chunk_type="faq",
                    metadata={"section": block.section},
                )
            )
            continue

        # نص عادي: بندمج البلوكات الصغيرة تحت نفس العنوان لحد ما نوصل للحد الأقصى
        body = "\n".join(block.lines)
        if pending_crumb is not None and (
            block.breadcrumb != pending_crumb
            or len("\n".join(pending)) + len(body) > max_chars
        ):
            if len("\n".join(pending)) >= min_chars or block.breadcrumb != pending_crumb:
                flush_pending()

        if pending_crumb is None:
            pending_crumb = block.breadcrumb
            pending_section = block.section
        pending.append(body)

    flush_pending()

    for index, chunk in enumerate(chunks):
        chunk.metadata.setdefault("source", source)
        chunk.metadata["chunk_index"] = index

    return chunks
