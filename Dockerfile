# ---- 1) Frontend: Vite + React + Tailwind -> radar/static ----
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/ ./frontend/
RUN cd frontend && npm install && npm run build

# ---- 2) Backend: FastAPI sirve la API y el estático ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY radar/ ./radar/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY seed/ ./seed/
COPY samples/panel/ ./samples/panel/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --from=frontend /app/radar/static ./radar/static
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/data /app/samples/raw
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "radar.app:app", "--host", "0.0.0.0", "--port", "8000"]
