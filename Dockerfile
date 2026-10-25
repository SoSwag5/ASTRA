FROM node:25-bookworm-slim@sha256:81db02c4b671288a03915da9534dbd54f96d0e7c24d80ccc54f5b36b2e684370 AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
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
