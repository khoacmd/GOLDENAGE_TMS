# Image backend dùng chung cho api / worker / scheduler / migrate (khác nhau ở command).
# Build đa kiến trúc: docker buildx build --platform linux/amd64,linux/arm64 backend
FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY optimization ./optimization
COPY app ./app
COPY worker ./worker

ARG RELEASE=dev
ENV TMS_RELEASE=$RELEASE TMS_ENV=prod TMS_LOG_JSON=true
RUN useradd --system --uid 10001 tms
USER tms
EXPOSE 8000
# API sau reverse proxy (nginx trong mạng nội bộ) → tin X-Forwarded-For để lấy IP thật.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "2", "--no-access-log"]
