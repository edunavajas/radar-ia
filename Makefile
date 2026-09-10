.DEFAULT_GOAL := help

.PHONY: help build dev test up down seed ingest index clean

help:
	@echo "Radar IA — objetivos:"
	@echo "  build    compila el frontend (Vite) en radar/static"
	@echo "  dev      backend local en http://localhost:8000"
	@echo "  test     tests (pytest)"
	@echo "  up       docker compose up --build"
	@echo "  seed     carga seed/seed.jsonl e indexa"
	@echo "  ingest   recolecta con Thordata (gasta creditos)"
	@echo "  index    trocea + embeddings + FTS5"

build:
	cd frontend && npm install && npm run build

dev: build
	.venv/bin/uvicorn radar.app:app --reload --port 8000

test:
	.venv/bin/pytest -q

up:
	docker compose up --build

down:
	docker compose down

seed:
	docker compose run --rm radar python -m radar.ingest --seed
	docker compose run --rm radar python -m radar.index

ingest:
	docker compose run --rm radar python -m radar.ingest --live

index:
	docker compose run --rm radar python -m radar.index

clean:
	rm -rf data radar/static frontend/dist .pytest_cache
