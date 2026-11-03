# JorMall Current Deployable

This folder is the flat deployable source package regenerated from the current official client export.

- Client slug: central-e-commerce-co-ltd
- Public chatbot route: /interactive-sms/
- Employee sales callback dashboard: /interactive-sms/sales-callbacks/
- Employee chat-history dashboard: /interactive-sms/chat-history/
- Pre-chat customer form collects customer name and mobile number only.
- Production Nginx snippet: deployment/nginx-interactive-sms.conf
- Runtime data is stored in Docker volumes declared in docker-compose.yml.
- New chat-history records are stored in PostgreSQL tables chat_conversations and chat_conversation_messages.
- Approved chatbot setup price is JOD 150 plus applicable sales tax and includes one month of hosting from activation.
- Hosting after the included month is available at JOD 30 for 1 month, JOD 75 for 3 months, JOD 140 for 6 months, or JOD 200 for 12 months, plus applicable sales tax.
- SMS, OTP, international SMS, API integration and WhatsApp API prices require approved data or a JorMall quotation; they must not reuse chatbot setup pricing.
- Streaming failures preserve useful partial answers and show graceful business fallbacks instead of temporary-unavailable system messages.
- Create a local .env from .env.example before starting the stack. Production reads its protected environment from /etc/jormall/apps/interactive-sms/production/app.env.
