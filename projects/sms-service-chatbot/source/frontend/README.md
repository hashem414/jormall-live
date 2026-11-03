# Frontend Assets

The standalone chatbot UI is served by FastAPI from:

- `app/templates/chat.html`
- `app/static/css/styles.css`
- `app/static/js/chat.js`

The embeddable launcher script is:

- `app/static/js/embed-widget.js`

Example website install snippet:

```html
<script async
  src="/sms-service-chatbot/embed/jormall-chatbot.js"
  data-chat-url="/sms-service-chatbot?embed=1"
  data-base-path="/sms-service-chatbot"
  data-launcher-label="Chat">
</script>
```
