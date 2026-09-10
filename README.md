# Radar IA

Buscador de **lo que se dice dentro** de los vídeos de YouTube, en cualquier
idioma. Preguntas en español («¿qué se ha dicho esta semana sobre X?») y
devuelve el minuto exacto donde se habla del tema, aunque el vídeo esté en
chino, japonés, coreano, alemán o inglés.

No es un buscador de vídeos: cada resultado apunta a un instante concreto.

> Estado: en construcción. **Fase 0 — probe de la API de Thordata.**
> El resto (ingesta, índice, buscador e interfaz) se construye de forma
> incremental después de confirmar la forma real de la respuesta de Thordata.

## Arranque (objetivo final)

```sh
cp .env.example .env   # rellenar tres valores
docker compose up
```

## Estructura prevista

- `ingest/` — habla con Thordata y llena la base de datos (se ejecuta a mano).
- `index/` — trocea transcripciones, genera embeddings y llena FTS5.
- `app/` — API FastAPI + interfaz; busca solo sobre lo que ya está en local.

## Probe

```sh
python scripts/probe.py [video_id] [lang]
```

Lanza una única petición real de transcripción, imprime la respuesta cruda y la
guarda en `samples/`. Se ejecuta antes de escribir la ingesta para no asumir la
forma de la respuesta.

## Licencia

MIT — ver [LICENSE](LICENSE).
