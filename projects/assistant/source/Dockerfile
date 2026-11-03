FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn && python -m playwright install --with-deps --only-shell chromium
COPY . .
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/flask_sessions /app/logs /app/exports/docx /app/exports/json /app/exports/bitly_logs \
        /app/assets /app/static /app/landing_pages \
    && chown -R app:app /app
USER 10001:10001
EXPOSE 2000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2000/healthz', timeout=3)"]
CMD ["gunicorn","--no-control-socket","--bind","0.0.0.0:2000","--workers","1","--threads","4","--timeout","300","--graceful-timeout","30","--keep-alive","5","app:app"]
