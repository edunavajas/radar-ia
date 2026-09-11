.DEFAULT_GOAL := help

.PHONY: help build dev test up down seed ingest index clean

help:
	@echo "Radar IA — objetivos:"
	@echo "  build    compila el frontend (Vite) en radar/static"
	@echo "  dev      backend local en http://localhost:8000"
	@echo "  test     tests (pytest, crea .venv si falta)"
	@echo "  up       docker compose up --build"
	@echo "  seed     carga seed/seed.jsonl e indexa"
	@echo "  ingest   recolecta con Thordata (gasta creditos)"
	@echo "  index    trocea + embeddings + FTS5"

.venv/.ready: requirements-dev.txt
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt
	@touch .venv/.ready

build:
	cd frontend && npm install && npm run build

dev: build .venv/.ready
	.venv/bin/uvicorn radar.app:app --reload --port 8000

test: .venv/.ready
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
