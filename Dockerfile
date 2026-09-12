FROM node:24-bookworm-slim AS web
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
COPY public ./public
COPY scripts/build.mjs ./scripts/build.mjs
COPY index.html tsconfig.json vite.config.ts ./
RUN node scripts/build.mjs

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend ./backend
COPY alembic.ini ./
COPY --from=web /app/dist ./dist
RUN useradd --create-home --uid 10001 realty && mkdir -p /app/data && chown -R realty:realty /app
USER realty
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "realty.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
