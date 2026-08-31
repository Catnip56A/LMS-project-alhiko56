FROM python:3.13-slim AS builder
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Use system Python so the venv path matches the final stage
ENV UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
WORKDIR /app

# Headless conversion of uploaded Office documents (.doc/.docx/.ppt/.pptx/.xls/.xlsx) to PDF
# for in-browser viewing — see lms/office_preview.py. R2 serves raw bytes with no equivalent
# to Drive's own document-rendering viewer, and browsers have no native renderer for Office
# formats (unlike PDF/images). Writer/Calc/Impress only (not the full `libreoffice` metapackage,
# which also pulls in Base/Draw/help files and is much larger) since those three cover every
# format this app accepts uploads for.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-calc libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    UV_PYTHON_DOWNLOADS=never

COPY . .

EXPOSE 8000
CMD ["gunicorn", "--config", "deploy/gunicorn_config.py", "app:app"]
