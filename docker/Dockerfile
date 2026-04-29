# syntax=docker/dockerfile:1.7
# ---------------- Stage 1: Tailwind build ------------------
# Pinned to BUILDPLATFORM (amd64 on GitHub runners) so we run the matching
# Tailwind binary natively without QEMU. CSS output is architecture-independent
# text, so stage 2 can still target linux/arm64 for the Pi.
FROM --platform=$BUILDPLATFORM alpine:3.19 AS tailwind
WORKDIR /build

ARG TAILWIND_VERSION=4.0.0
ARG TARGETARCH
RUN apk add --no-cache curl && \
    case "$(uname -m)" in \
        x86_64)  TW_ARCH=x64   ;; \
        aarch64) TW_ARCH=arm64 ;; \
        *) echo "unsupported arch: $(uname -m)" && exit 1 ;; \
    esac && \
    curl -sLO "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-${TW_ARCH}" && \
    chmod +x "tailwindcss-linux-${TW_ARCH}" && \
    mv "tailwindcss-linux-${TW_ARCH}" /usr/local/bin/tailwindcss

COPY tailwind.config.js ./
COPY app/web/static/css/tailwind.input.css ./input.css
COPY app/web/templates ./app/web/templates
RUN tailwindcss -i ./input.css -o ./output.css --minify

# ---------------- Stage 2: Runtime --------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --no-create-home app

COPY pyproject.toml ./
# Install only runtime deps (no [dev] extras)
RUN pip install --no-cache-dir -e ".[]"

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

# Pull built CSS from stage 1 (no Node runtime needed in final image)
COPY --from=tailwind /build/output.css ./app/web/static/css/tailwind.output.css

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8080"]
