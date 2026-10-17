FROM node:24-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock.txt && playwright install --with-deps chromium
COPY backend ./backend
COPY scripts ./scripts
COPY THIRD_PARTY_NOTICES.md ./THIRD_PARTY_NOTICES.md
COPY --from=frontend /ui/dist ./frontend/dist
COPY THIRD_PARTY_NOTICES.md ./frontend/dist/third-party-notices.txt
RUN mkdir -p /app/data
ENV BIND_HOST=0.0.0.0
EXPOSE 8787
CMD ["python","-m","uvicorn","backend.main:app","--host","0.0.0.0","--port","8787","--no-access-log"]
