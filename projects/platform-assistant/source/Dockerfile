FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app && chown -R app:app /app
USER 10001:10001
EXPOSE 8002
CMD ["python","-m","uvicorn","fastapi_app.main:app","--host","0.0.0.0","--port","8002","--workers","1"]
