FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/intervention-engine /tmp/intervention-engine

RUN pip install --no-cache-dir /tmp/intervention-engine \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2.6" \
    "pydantic-settings>=2.3" \
    "httpx>=0.27" \
    "sqlalchemy[asyncio]>=2.0" \
    "asyncpg>=0.29" \
    "redis>=5.0" \
    "cryptography>=42" \
    && rm -rf /tmp/intervention-engine

COPY apps/cloud-api/app ./app
COPY data/actions/actions.json ./data/actions/actions.json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
