FROM python:3.12-slim AS builder
ENV UV_LINK_MODE=copy
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/.venv /app/.venv
COPY . .
RUN addgroup --system --gid 10001 django && adduser --system --uid 10001 --ingroup django django && mkdir -p /app/staticfiles /app/media /var/run/celery && chown -R django:django /app /var/run/celery
USER django
EXPOSE 8000
CMD ["gunicorn","config.asgi:application","-k","uvicorn.workers.UvicornWorker","--bind","0.0.0.0:8000","--workers","4","--timeout","60","--access-logfile","-"]
