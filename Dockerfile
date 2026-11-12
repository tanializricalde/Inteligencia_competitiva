# syntax=docker/dockerfile:1.7
FROM node:20-bookworm-slim AS assets
WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --network-concurrency 4
COPY frontend/ ./
RUN NODE_OPTIONS=--max-old-space-size=1536 pnpm build

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src \
    DJANGO_SETTINGS_MODULE=config.settings.production PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && \
    playwright install --with-deps chromium
COPY manage.py ./
COPY config.example.toml ./
COPY feature_rules/ ./feature_rules/
COPY src/ ./src/
COPY --from=assets /build/src/static/dist/ ./src/static/dist/
RUN mkdir -p /app/data /app/evidence /app/media /app/staticfiles && \
    python manage.py collectstatic --noinput && \
    chown -R app:app /app/data /app/evidence /app/media /app/staticfiles
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "60", "--access-logfile", "-"]

