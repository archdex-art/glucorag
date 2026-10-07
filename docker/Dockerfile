# API + monitoring dashboard image. Model artifacts and the SQLite DB are mounted, never baked in:
#   docker compose -f docker/compose.yaml up --build
# Stage 1 builds the dashboard (web/ -> glucorag/api/static); stage 2 is the Python runtime.
FROM node:22-alpine AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /bin/uv
WORKDIR /app

COPY pyproject.toml README.md ./
COPY glucorag/ ./glucorag/
COPY --from=web /src/glucorag/api/static/ ./glucorag/api/static/
# CPU-only torch wheels keep the image small; the model is tiny and runs in ~1 ms/cycle on CPU.
RUN uv pip install --system --no-cache --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cpu . \
    && test -f "$(python -c 'import glucorag.api.web as w; print(w.DEFAULT_WEB_DIR)')/index.html" \
    && useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /var/lib/glucorag && chown appuser /var/lib/glucorag

USER appuser
ENV GLUCORAG_HOST=0.0.0.0 \
    GLUCORAG_PORT=8000 \
    GLUCORAG_DB_PATH=/var/lib/glucorag/glucorag.sqlite \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"GLUCORAG_PORT\"]}/healthz')"
CMD ["glucorag-serve"]
