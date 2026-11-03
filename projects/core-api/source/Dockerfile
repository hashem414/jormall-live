FROM python:3.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt beautifulsoup4 python-docx openai playwright requests PyJWT \
    && python -m playwright install --with-deps chromium
COPY . .
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app && chown -R app:app /app
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn","-w","1","--threads","4","-b","0.0.0.0:8000","run:app"]
