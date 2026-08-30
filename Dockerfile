FROM node:24-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci

COPY frontend/ ./

RUN npm run build

FROM python:3.12.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY backend/ ./backend

COPY --from=builder /app/dist ./frontend/dist

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
