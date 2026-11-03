FROM node:22-alpine AS ui-build

WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    YOTTAFLEX_DATA_DIR=/app/data/full \
    YOTTAFLEX_GROUND_TRUTH_DIR=/app/ground_truth/full \
    YOTTAFLEX_AI_LOG_PATH=/app/reports/copilot_interactions.jsonl

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY config/ ./config/
COPY docs/ ./docs/
COPY schema/ ./schema/
COPY docker/api-entrypoint.sh /usr/local/bin/yottaflex-entrypoint
RUN python -m pip install --no-cache-dir '.[ai]' \
    && chmod +x /usr/local/bin/yottaflex-entrypoint \
    && mkdir -p /app/data /app/ground_truth /app/reports

EXPOSE 8000
ENTRYPOINT ["yottaflex-entrypoint"]

FROM nginx:alpine AS ui

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=ui-build /ui/dist/ /usr/share/nginx/html/
EXPOSE 80
