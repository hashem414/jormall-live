FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 5056
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5056", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
