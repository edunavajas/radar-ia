# ---- 1) Frontend: Vite + React + Tailwind -> radar/static ----
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/ ./frontend/
RUN cd frontend && npm install && npm run build

# ---- 2) Backend: FastAPI sirve la API y el estático ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY radar/ ./radar/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY seed/ ./seed/
COPY samples/panel/ ./samples/panel/
COPY --from=frontend /app/radar/static ./radar/static
RUN mkdir -p /app/data /app/samples/raw
EXPOSE 8000
CMD ["uvicorn", "radar.app:app", "--host", "0.0.0.0", "--port", "8000"]
