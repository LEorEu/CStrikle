FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

COPY --chown=app:app server ./server
COPY --chown=app:app static ./static
COPY --chown=app:app data ./data

USER app

EXPOSE 8620

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8620/api/meta', timeout=3)"]

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8620", "--proxy-headers", "--forwarded-allow-ips=*"]
