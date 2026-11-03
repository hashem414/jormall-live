"""طبقة قاعدة البيانات: connection pool + تسجيل نوع vector."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None

# آخر لحظة استُخدم فيها كل اتصال — لتقرير هل بدنا نفحصه قبل التسليم
_last_used: dict[int, float] = {}

# اتصال استُخدم خلال هذه المدة بنعتبره حيّاً بدون فحص.
# القيمة أقصر بكثير من max_idle، فالاتصال الخامل فعلاً بينفحص عادي.
CHECK_AFTER_IDLE_SECONDS = 20.0


def _configure(conn: psycopg.Connection) -> None:
    """
    يُنفَّذ لكل اتصال جديد. بنسجّل نوع vector للقراءة،
    بس بنتساهل لو الإكستنشن لسا مش منصّب (أول تشغيل قبل init) —
    الكتابة بتشتغل بكل الأحوال لأننا بنمرّر المتجه كنص مع ::vector.
    """
    try:
        register_vector(conn)
    except Exception as exc:  # pragma: no cover
        logger.debug("register_vector تخطّي: %s", exc)

    # دقة بحث HNSW بتنضبط مرة وحدة لكل اتصال بدل SET LOCAL مع كل استعلام.
    # السبب: SET LOCAL بدّه ترانزاكشن، والترانزاكشن بتكلّف BEGIN + COMMIT —
    # رحلتين زيادة على قاعدة بعيدة، مع كل بحث.
    # لازم commit بعدها: psycopg بيفتح ترانزاكشن ضمنية، والـ pool بيرفض
    # أي اتصال بيرجع من configure وهو INTRANS. الإعداد session-level فبيضل بعد الـ commit.
    try:
        conn.execute("SET hnsw.ef_search = 100")
        conn.commit()
    except Exception as exc:  # pragma: no cover
        logger.debug("hnsw.ef_search غير مدعوم: %s", exc)
        conn.rollback()


def _check_if_idle(conn: psycopg.Connection) -> None:
    """
    فحص الاتصال قبل التسليم — بس لما يكون خامل فترة.

    الفحص الدائم كان بيكلّف رحلة كاملة قبل **كل** استعلام. على قاعدة بعيدة
    (Neon بأوهايو) هاي كانت ~٦ رحلات فاضية بالرسالة الوحدة. المشكلة اللي
    انحطّ لها الفحص (السيرفر بيسكّر الاتصالات الخاملة) بتصير بعد خمول،
    فبنفحص عند الخمول بس — والمحادثة النشطة ما بتدفع أي رحلة زيادة.
    """
    if time.monotonic() - _last_used.get(id(conn), 0.0) < CHECK_AFTER_IDLE_SECONDS:
        return
    ConnectionPool.check_connection(conn)


def to_pgvector(values: Sequence[float]) -> str:
    """
    يحوّل قائمة أرقام لصيغة نصية بيفهمها pgvector: '[0.1,0.2,...]'
    بنستخدم النص بدل الاعتماد على adapter عشان الكود يشتغل مع أي إصدار
    من pgvector-python وبدون numpy.
    """
    return "[" + ",".join(f"{float(v):.8g}" for v in values) + "]"


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            configure=_configure,
            # ── مهم مع PostgreSQL السحابي (Neon/Supabase) ──
            # هدول بينامو وبيسكّروا الاتصالات الخاملة، فالـ pool بيسلّم اتصال ميت
            # وأول طلب بعد فترة هدوء بيفشل بـ "server closed the connection unexpectedly".
            check=_check_if_idle,                   # فحص عند الخمول فقط، مش كل مرة
            max_idle=120.0,                         # سكّر الخامل قبل ما السيرفر يسكّره
            max_lifetime=1800.0,                    # جدّد الاتصالات كل نص ساعة
            reconnect_timeout=30.0,
            open=True,
        )
        logger.debug("connection pool opened")
    return _pool


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """اتصال من الـ pool مع commit تلقائي و rollback عند الخطأ."""
    with get_pool().connection() as conn:
        try:
            yield conn
        finally:
            # بنسجّل وقت الاستخدام حتى الفحص القادم يعرف إذا الاتصال خمل
            _last_used[id(conn)] = time.monotonic()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def init_schema(schema_path: str | Path = "sql/schema.sql") -> None:
    """ينشئ الجداول والإندكسات لو مش موجودة (idempotent)."""
    sql = Path(schema_path).read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(sql)  # type: ignore[arg-type]
    logger.info("schema initialised from %s", schema_path)


def healthcheck() -> dict:
    """فحص سريع: الاتصال شغال؟ الإكستنشن موجود؟ كم شانك عنا؟"""
    with get_conn() as conn:
        ext = conn.execute(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        counts = conn.execute(
            """
            SELECT
                (SELECT count(*) FROM documents) AS documents,
                (SELECT count(*) FROM chunks)    AS chunks,
                (SELECT count(*) FROM chunks WHERE embedding IS NULL) AS missing_embeddings
            """
        ).fetchone()
    return {
        "database": "ok",
        "pgvector": bool(ext),
        **(counts or {}),
    }
