# AV Nexus backend image (uv-managed, multi-stage).
# Build context: ./backend

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AVNEXUS_ENV=production

WORKDIR /app

# Sync locked dependencies first (leverages cache across rebuilds).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code (av_nexus package only).
COPY av_nexus ./av_nexus

EXPOSE 8000

# The factory is used so the app is created via create_app().
CMD ["uv", "run", "--no-sync", "uvicorn", "av_nexus.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]