
# 🤖 JorMall Internal Assistant - Chatbot

This is a secure, session-based internal Flask web application designed to support JorMall's SMS marketing services through an AI-powered chatbot. It assists in answering client questions, generating SMS campaigns, analyzing company profiles, sending chat transcripts via email, and retrieving content from DOCX/PDF files.

---

## 📌 Overview

This assistant supports the following core functions:

- AI Chat (OpenAI GPT-4 + document RAG)
- SMS campaign, profile, marketing-plan, and industry-tailored Platform Benefits generation
- Secure multi-user login
- HTML front-end UI with static routing
- Email delivery for chat sessions
- DOCX/PDF parsing for content assistance

---

## 🧩 Tech Stack

- **Backend:** Python + Flask
- **Frontend:** HTML (served from `static/`)
- **AI Engine:** OpenAI GPT-4 + Embeddings (`text-embedding-3-large`)
- **Data Storage:** Session-based + JSON logs
- **Email:** SMTP for transcript delivery
- **Document Parsing:** `PyMuPDF`, `python-docx`, `mammoth`
- **Authentication:** Session + username/password mapping

---

## 🔐 User Management

- Users are authenticated by the configured central user-directory service.
- No user passwords are stored in this repository.
- Sessions are stored server-side and expire after logout.

---

## 🌐 Frontend (HTML UI)

- The UI is written in HTML and served from the `static/` folder.
- The home page is accessible via `/`, and login is handled via `/login`.
- Chat interactions and document downloads are served dynamically via Flask routes.

---

## 🏁 Getting Started

### 1. Clone and Navigate
```bash
cd /path/to/your/project
```

### 2. Set Up Python Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

<details>
<summary>Click to view <code>requirements.txt</code></summary>

```txt
flask
flask-cors
flask-session
python-dotenv
numpy
python-docx
PyMuPDF
mammoth
openai
```
</details>

### 4. Add `.env` Configuration

Copy `.env.example` to `.env` for local development. In production, inject the
same values with your hosting platform's secret manager; do not bake `.env` into
the image.

```env
FLASK_SECRET_KEY=your-secret-key
USER_DIRECTORY_URL=http://user-directory:18101
USER_DIRECTORY_TOKEN=your-user-directory-token
SMTP_SENDER=noreply@jormall.com
SMTP_SERVER=smtp.yourmailhost.com
SMTP_PORT=587
SMTP_PASSWORD=your-smtp-password
OPENAI_API_KEY=your-openai-key
BITLY_API_KEY=your-bitly-key
```

---

## 🚀 Running the App

```bash
python app.py
```

The development server starts at:
```
http://127.0.0.1:2000
```

For production, use the included Docker image and publish container port 2000:

```bash
docker build -t jormall-assistant .
docker run --env-file .env -p 2000:2000 jormall-assistant
```

The container runs Gunicorn as an unprivileged user and exposes `/healthz` for
liveness checks. `/readyz` returns HTTP 200 only when the core OpenAI, session,
user-directory, and document configuration is present.

Persist or mount `/app/logs`, `/app/exports`, and `/app/flask_sessions` if chat
history, generated reports, and sessions must survive container replacement.
When sharing login cookies across subdomains, set `SESSION_COOKIE_DOMAIN`
explicitly and use a shared session store/volume. Leave it empty for a host-only
cookie. Set `CORS_ALLOWED_ORIGINS` only when cross-origin browser requests are
required. For plain-HTTP local development only, set
`SESSION_COOKIE_SECURE=false`; keep it `true` in production.

---

## 🔄 Key Functional Routes

| Route                         | Method | Purpose                                  |
|------------------------------|--------|------------------------------------------|
| `/login`                     | POST   | Authenticates user session               |
| `/chat`                      | POST   | Submits user question to AI assistant    |
| `/api/generate-campaign`     | POST   | Generates campaign DOCX + JSON           |
| `/api/generate-profile`      | POST   | Generates company profile DOCX + JSON    |
| `/api/generate-platform-benefits` | POST | Generates industry-tailored Platform Benefits DOCX + JSON |
| `/send-email`                | POST   | Sends email with HTML body               |
| `/get-docx-content?file=x`   | GET    | Returns clean HTML from DOCX             |
| `/documents/<filename>`      | GET    | Downloads uploaded files                 |
| `/exports/docx/<filename>`   | GET    | Downloads generated DOCX output          |
| `/logout`                    | POST   | Ends session                             |

---

## 🧠 Chatbot Logic

- Embeds document chunks at startup (PDFs & DOCX from `documents/` folder).
- Finds top 20 similar sections to the user's input using cosine similarity.
- Builds a system prompt based on user profile and retrieved context.
- Uses `GPT-4o` or `GPT-4` for generating a tailored reply.

---

## 📥 Campaign, Profile & Platform Benefits Generation

- Inputs required:
  - Company Name
  - Company URL
  - Campaign Brief (for SMS only)
- Optional: Bitly Link and Phone Number
- Generates:
  - 📄 DOCX Report (via `generate_ai_docx`)
  - 📊 JSON Summary

Platform Benefits reports add an industry selector and use the same shared Client Insights Word formatting as Profile Report and Marketing Plan. The previous dedicated Platform Benefits Word template is no longer used. The report can be generated in English or Arabic and includes tailored SMS use cases, segmentation, execution steps, KPIs, recommendations, compliance notes, and JorMall platform benefits.

---

## 📧 Email Feature

- Sends AI transcript to an email address provided by the user.
- Configurable via SMTP in `.env`.
- Includes HTML and plaintext fallback for compatibility.

---

## 📁 Folder Structure

```
├── app.py
├── .env.example
├── static/                 # Frontend HTML
├── assets/images/         # Icons and logos
├── documents/             # Input PDFs/DOCX for RAG
├── exports/
│   ├── docx/              # Exported campaign/profile reports
│   └── json/              # Analysis metadata
├── flask_sessions/        # Server-side session cache
├── logs/                  # JSON logs of chat sessions
├── requirements.txt
```

## ✅ Pre-deployment Check

Before routing production traffic:

1. Supply all values reported by `/readyz` as missing.
2. Confirm the user-directory service is reachable from the container.
3. Verify the OpenAI project can access `gpt-5.5` and
   `text-embedding-3-large`.
4. Configure SMTP and Bitly only if those UI features will be used.
5. Use HTTPS; session cookies are marked `Secure`.

---

## 🧾 License

This project is **proprietary** and maintained internally by JorMall.  
Unauthorized distribution is prohibited.

---

## 🧑‍💻 Maintained by

**JorMall Team**  
📅 Last Updated: **Thursday, 19 June 2025**  
🌐 [www.jormall-jo.com](https://www.jormall-jo.com)  
📧 [info@jormall.com](mailto:info@jormall.com)  
📞 +962 6 5855703 / 6 5823961 / 6 5858687  
📱 +962 77 9937272  
📠 +962 6 5858951
