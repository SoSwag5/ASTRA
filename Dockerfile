FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir --upgrade pip==26.2 && pip install --no-cache-dir -r requirements.lock.txt && playwright install --with-deps chromium
COPY backend ./backend
COPY scripts ./scripts
COPY THIRD_PARTY_NOTICES.md ./THIRD_PARTY_NOTICES.md
COPY --from=frontend /ui/dist ./frontend/dist
COPY THIRD_PARTY_NOTICES.md ./frontend/dist/third-party-notices.txt
RUN mkdir -p /app/data
ENV BIND_HOST=0.0.0.0
EXPOSE 8787
CMD ["python","-m","uvicorn","backend.main:app","--host","0.0.0.0","--port","8787","--no-access-log"]
