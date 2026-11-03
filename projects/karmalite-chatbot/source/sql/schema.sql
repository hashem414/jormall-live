-- ============================================================
-- Karmalite RAG — PostgreSQL schema (pgvector)
-- ملاحظة: أبعاد المتجه 1536 = text-embedding-3-small
-- لو غيّرت موديل الإمبيدنج، غيّر الرقم هون وأعد التهيئة.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------
-- 1) المستندات المصدرية (ملف = مستند)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    source        TEXT        NOT NULL UNIQUE,      -- مسار الملف
    title         TEXT,
    content_hash  TEXT        NOT NULL,             -- sha256 لتفادي إعادة الإدخال بدون تغيير
    lang          TEXT        NOT NULL DEFAULT 'ar+en',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 2) الشانكس + المتجهات
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id            BIGSERIAL PRIMARY KEY,
    document_id   BIGINT      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index   INT         NOT NULL,
    breadcrumb    TEXT        NOT NULL DEFAULT '',  -- مسار العناوين: "الخدمات > الحقن التجميلية"
    content       TEXT        NOT NULL,             -- النص اللي بينحط بالبرومبت
    search_text   TEXT        NOT NULL,             -- نسخة مُطبّعة للبحث النصي (تطبيع عربي)
    chunk_type    TEXT        NOT NULL DEFAULT 'prose', -- prose | table_row | faq
    metadata      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    token_count   INT         NOT NULL DEFAULT 0,
    embedding     VECTOR(1536),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

-- بحث دلالي (cosine) — HNSW أسرع وأدق من IVFFlat لهذا الحجم
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- بحث كلمات مفتاحية (simple config لأن العربية غير مدعومة بـ stemmer افتراضي)
CREATE INDEX IF NOT EXISTS chunks_fts_idx
    ON chunks USING gin (to_tsvector('simple', search_text));

-- بحث تقريبي للأخطاء الإملائية / الأسماء التجارية
CREATE INDEX IF NOT EXISTS chunks_trgm_idx
    ON chunks USING gin (search_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id);
CREATE INDEX IF NOT EXISTS chunks_metadata_idx    ON chunks USING gin (metadata);

-- ------------------------------------------------------------
-- 3) المحادثات والرسائل (ذاكرة قصيرة المدى + تدقيق)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT        NOT NULL UNIQUE,
    channel     TEXT        NOT NULL DEFAULT 'web',   -- web | instagram | messenger | phone
    lang        TEXT,
    metadata    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT      NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content         TEXT        NOT NULL,
    retrieved_ids   BIGINT[]    NOT NULL DEFAULT '{}',  -- شو استرجع لهاي الرسالة (للتدقيق)
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_conversation_idx
    ON messages (conversation_id, created_at);

-- ------------------------------------------------------------
-- 4) العملاء المحتملين (الهدف الأساسي للبوت: اسم + رقم)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leads (
    id               BIGSERIAL PRIMARY KEY,
    conversation_id  BIGINT      REFERENCES conversations(id) ON DELETE SET NULL,
    full_name        TEXT        NOT NULL,
    phone            TEXT        NOT NULL,           -- مُطبّع: 9627XXXXXXXX
    service_interest TEXT,
    preferred_time   TEXT,
    gender           TEXT,                           -- male | female | unknown
    notes            TEXT,
    status           TEXT        NOT NULL DEFAULT 'new', -- new | contacted | booked | lost
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS leads_status_idx  ON leads (status, created_at DESC);
CREATE INDEX IF NOT EXISTS leads_phone_idx   ON leads (phone);

-- ------------------------------------------------------------
-- 4b) طلبات المواعيد (الزبون بيختار من الكالندر، الاستقبال بيأكد)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    id               BIGSERIAL PRIMARY KEY,
    conversation_id  BIGINT      REFERENCES conversations(id) ON DELETE SET NULL,
    lead_id          BIGINT      REFERENCES leads(id) ON DELETE SET NULL,
    full_name        TEXT        NOT NULL,
    phone            TEXT        NOT NULL,           -- مُطبّع: 9627XXXXXXXX
    service          TEXT,
    doctor_id        TEXT,
    appointment_date DATE        NOT NULL,
    appointment_time TIME        NOT NULL,
    gender           TEXT        NOT NULL DEFAULT 'unknown',
    notes            TEXT,
    -- requested = طلب بانتظار تأكيد الاستقبال (ما بينحسب موعد مؤكد)
    status           TEXT        NOT NULL DEFAULT 'requested'
                     CHECK (status IN ('requested','confirmed','cancelled','completed','no_show')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- تتبّع الإلغاء (مين ألغى ومتى) — إضافة آمنة على قواعد موجودة
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS cancelled_at   TIMESTAMPTZ;
-- chat | self-service (المريض) · admin (العيادة)
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS cancelled_by   TEXT;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS cancel_reason  TEXT;

-- الموعد المنقول حالته 'rescheduled' مش 'cancelled' — إلغاء وإعادة جدولة شيئان مختلفان
-- إدارياً، وخلطهما بيشوّه إحصائيات الإلغاء.
ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_status_check;
ALTER TABLE appointments ADD CONSTRAINT appointments_status_check
    CHECK (status IN ('requested','confirmed','cancelled','rescheduled','completed','no_show'));

-- البريد الإلكتروني — يُستخدم للتحقق قبل تثبيت الطلب
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS doctor_id TEXT;

-- Existing appointments receive the same deterministic assignment as new ones.
UPDATE appointments
SET doctor_id = CASE
    WHEN service IN ('botox_full_face','fillers','profhilo','skin_boosters','lpg_body',
                     'cryolipolysis','fat_freezing_360','exilis','emsculpt','ultratone_body',
                     'carboxy_therapy','body_peel','spray_tan','solarium') THEN 'adeeb'
    WHEN service IN ('laser_full_body_women','laser_full_body_men','laser_single_area',
                     'laser_tattoo_removal','hydrafacial','dermapen','microneedling_rf',
                     'fractional_co2','endermolift','ultratone_face','chemical_peel','hifu',
                     'prp_face','prp','hair_mesotherapy','dermatology_consultation') THEN 'miral'
    WHEN service IN ('plastic_surgery_consultation','aesthetic_surgery_consultation') THEN 'qasim_wreikat'
    WHEN service IN ('gynecology_consultation','pregnancy_postpartum','intimate_wellness',
                     'aesthetic_gynecology','consultation','not_sure') THEN 'leen'
    ELSE doctor_id
END
WHERE doctor_id IS NULL;

-- Preserve legacy overlapping appointments without inventing a second clinician.
WITH duplicate_assignments AS (
    SELECT id, row_number() OVER (
        PARTITION BY appointment_date, appointment_time, doctor_id ORDER BY id
    ) AS position
    FROM appointments
    WHERE doctor_id IS NOT NULL AND status IN ('requested', 'confirmed')
)
UPDATE appointments a
SET doctor_id = NULL
FROM duplicate_assignments d
WHERE a.id = d.id AND d.position > 1;

-- ------------------------------------------------------------
-- قواعد ازدحام الخانة الواحدة
-- ------------------------------------------------------------
-- القاعدة القديمة كانت: موعد واحد بكل خانة زمنية. العيادة بتشتغل بأكثر من
-- غرفة/جهاز، فصار المسموح: نفس الوقت لأكثر من مريض **بشرط اختلاف الخدمة**
-- (خدمة واحدة = غرفة واحدة)، و**اختلاف الشخص** (ما بيقدر يكون بغرفتين بنفس اللحظة).
DROP INDEX IF EXISTS appointments_slot_uniq;

-- خدمة واحدة لكل خانة. COALESCE ضروري: الـ NULL بالفهارس الفريدة بيعتبر
-- مميّزاً عن غيره، فبدونه صفوف بخدمة فاضية بتتسلّل من القيد.
CREATE UNIQUE INDEX IF NOT EXISTS appointments_slot_service_uniq
    ON appointments (appointment_date, appointment_time, COALESCE(service, ''))
    WHERE status IN ('requested', 'confirmed');

-- نفس الشخص ما بيحجز خانتين بنفس اللحظة — لا برقمه ولا بإيميله
CREATE UNIQUE INDEX IF NOT EXISTS appointments_slot_phone_uniq
    ON appointments (appointment_date, appointment_time, phone)
    WHERE status IN ('requested', 'confirmed');

CREATE UNIQUE INDEX IF NOT EXISTS appointments_slot_email_uniq
    ON appointments (appointment_date, appointment_time, lower(email))
    WHERE status IN ('requested', 'confirmed') AND email IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS appointments_slot_doctor_uniq
    ON appointments (appointment_date, appointment_time, doctor_id)
    WHERE status IN ('requested', 'confirmed') AND doctor_id IS NOT NULL;

-- ------------------------------------------------------------
-- 4c) رموز التحقق بالبريد — بتمنع الحجز العشوائي بإيميلات وهمية
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_verifications (
    id               BIGSERIAL PRIMARY KEY,
    conversation_id  BIGINT      REFERENCES conversations(id) ON DELETE CASCADE,
    email            TEXT        NOT NULL,
    code_hash        TEXT        NOT NULL,   -- sha256 — ما بنخزّن الرمز خام
    attempts         INT         NOT NULL DEFAULT 0,
    verified_at      TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS email_verif_lookup_idx
    ON email_verifications (conversation_id, lower(email), created_at DESC);
-- للتحقق من عدد الرموز المرسلة بالساعة (حدّ ضد الإغراق)
CREATE INDEX IF NOT EXISTS email_verif_rate_idx
    ON email_verifications (lower(email), created_at DESC);

CREATE INDEX IF NOT EXISTS appointments_agenda_idx
    ON appointments (appointment_date, appointment_time);
CREATE INDEX IF NOT EXISTS appointments_status_idx
    ON appointments (status, created_at DESC);

-- ------------------------------------------------------------
-- 4c) صادر الإشعارات (Outbox)
-- لما العيادة تلغي موعد، بننشئ إشعاراً للمريض هون. تسليمه عبر SMS
-- بيحتاج ربط ببوابة الرسائل — لحد ذلك بيضل pending وبينعرض للمريض بالشات.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id             BIGSERIAL PRIMARY KEY,
    appointment_id BIGINT      REFERENCES appointments(id) ON DELETE SET NULL,
    phone          TEXT        NOT NULL,
    kind           TEXT        NOT NULL,              -- clinic_cancelled | reminder | ...
    language       TEXT        NOT NULL DEFAULT 'ar' CHECK (language IN ('ar','en')),
    body_ar        TEXT        NOT NULL,
    body_en        TEXT        NOT NULL,
    sms_body_ar    TEXT,
    sms_body_en    TEXT,
    payload        JSONB       NOT NULL DEFAULT '{}'::jsonb,   -- الأوقات المقترحة
    status         TEXT        NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','processing','submitted','submitted_unverified',
                                     'delivered','sent','failed')),
    provider       TEXT,
    provider_reference TEXT,
    provider_response  TEXT,
    response_verified  BOOLEAN,
    attempts       INTEGER     NOT NULL DEFAULT 0,
    last_error     TEXT,
    next_attempt_at TIMESTAMPTZ DEFAULT now(),
    processing_started_at TIMESTAMPTZ,
    submitted_at   TIMESTAMPTZ,
    delivered_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at        TIMESTAMPTZ,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ترقية آمنة لقواعد البيانات الموجودة قبل ربط JOSMS.
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'ar';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS sms_body_ar TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS sms_body_en TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS provider TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS provider_reference TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS provider_response TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS response_verified BOOLEAN;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS last_error TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE notifications
SET sms_body_ar = COALESCE(sms_body_ar, body_ar),
    sms_body_en = COALESCE(sms_body_en, body_en)
WHERE sms_body_ar IS NULL OR sms_body_en IS NULL;

ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_status_check;
ALTER TABLE notifications ADD CONSTRAINT notifications_status_check
    CHECK (status IN ('pending','processing','submitted','submitted_unverified',
                      'delivered','sent','failed'));

ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_language_check;
ALTER TABLE notifications ADD CONSTRAINT notifications_language_check
    CHECK (language IN ('ar','en'));

CREATE INDEX IF NOT EXISTS notifications_pending_idx
    ON notifications (status, next_attempt_at, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS notifications_appointment_kind_uniq
    ON notifications (appointment_id, kind)
    WHERE appointment_id IS NOT NULL;

-- ------------------------------------------------------------
-- 4d) Appointment lifecycle email outbox
-- Each appointment event is unique, so repeated status updates cannot resend it.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointment_email_events (
    id             BIGSERIAL PRIMARY KEY,
    appointment_id BIGINT      NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    kind           TEXT        NOT NULL,
    recipient      TEXT        NOT NULL,
    subject        TEXT        NOT NULL,
    text_body      TEXT        NOT NULL,
    status         TEXT        NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','sending','sent','failed')),
    attempts       INTEGER     NOT NULL DEFAULT 0,
    last_error     TEXT,
    sent_at        TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (appointment_id, kind)
);

CREATE INDEX IF NOT EXISTS appointment_email_events_status_idx
    ON appointment_email_events (status, created_at);

-- ------------------------------------------------------------
-- 5) التصعيدات (شكاوى / طوارئ طبية)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalations (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT      REFERENCES conversations(id) ON DELETE SET NULL,
    level           TEXT        NOT NULL,   -- reception | manager | medical | emergency
    reason          TEXT        NOT NULL,
    handled         BOOLEAN     NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- بيانات التواصل لحظة التصعيد. مخزّنة هون (مش join وقت العرض) لأنها لقطة
-- وقت الحادثة — لو المريض غيّر رقمه لاحقاً بدنا الرقم اللي كان وقت الطوارئ.
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS phone     TEXT;

CREATE INDEX IF NOT EXISTS escalations_open_idx ON escalations (handled, created_at DESC);
CREATE INDEX IF NOT EXISTS escalations_phone_idx ON escalations (phone);
