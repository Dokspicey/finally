# FinAlly — multi-stage container build.
#
# Stage 1 (frontend-build): builds the Next.js static export from `frontend/`
# using `npm ci && npm run build`. The export lands in `frontend/out/` which
# Stage 2 copies to `/app/static/`. FastAPI then mounts that directory and
# falls back to `index.html` for any non-`/api/*` GET so the SPA routes work
# (see the static mount block at the bottom of `backend/app/main.py`).

FROM node:20-slim AS frontend-build
WORKDIR /frontend

# Install deps first (better layer cache) then copy the rest.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2 — Python backend. Installs `uv`, syncs deps from the lockfile,
# copies the frontend static export from Stage 1, and serves FastAPI on :8000.
# SQLite lives under /app/db (bind-mounted from host).

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    FINALLY_STATIC_DIR=/app/static

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-install-project

COPY backend/ ./
RUN uv sync --frozen

COPY --from=frontend-build /frontend/out /app/static

RUN mkdir -p /app/db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
