# Document ingestion audit

The three supplied Word documents were inspected before integration.

| Document | Extracted text | Embedded images | Retrieval role |
|---|---:|---:|---|
| `TRC_SMS_Regulations_2024_Reference_AR.docx` | ~1,058 words | 0 | Primary Arabic regulatory reference, Articles 1–8 |
| `TRC_SMS_Regulations_2024_Reference_EN.docx` | ~1,043 words | 0 | English translation/reference, Articles 1–8 |
| `Platform_User_Manual_2025_+_ALT.docx` | ~2,892 words | 27 | Platform procedures and operating guidance |

Arabic and English extraction is readable. The regulation files contain no screenshot-only material.

All 27 manual images were visually inspected. They are interface illustrations for login, menus, message generation, contact/category management, notepad imports, searches, scheduled messages, birthday templates, sender requests, and password changes. Their operational information is also described by the surrounding searchable text. No supplemental OCR file is required for the current version. Re-run this audit if the manual is replaced.

The ingestion metadata groups both TRC files under `trc_bulk_sms_2024`. Runtime retrieval prefers the language of the user's question and removes duplicate TRC article matches, preventing the translation pair from being treated as two independent rules.

