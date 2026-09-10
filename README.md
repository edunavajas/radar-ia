# Radar IA

Buscador de **lo que se dice dentro** de los vídeos de YouTube, en cualquier
idioma. Preguntas en español («¿qué se ha dicho esta semana sobre X?») y
devuelve **el minuto exacto** donde se habla del tema, aunque el vídeo esté en
chino, japonés, coreano, alemán o inglés.

No es un buscador de vídeos: cada resultado apunta a un instante concreto.

## Qué necesitas

- Una **URL y una key** de cualquier API de IA compatible con OpenAI — sirve
  para dos cosas: los *embeddings* que entienden el contenido en cualquier
  idioma, y el LLM que redacta la respuesta en español.
- Un **token de Thordata** — sirve para conseguir las transcripciones de YouTube
  sin que YouTube te bloquee.

## Arranque

```sh
cp .env.example .env    # rellena THORDATA_TOKEN, AI_API_BASE_URL y AI_API_KEY
docker compose up
```

Abre http://localhost:8000. La base de datos vive en un volumen, así que
sobrevive a los reinicios.

Para ver la app con contenido:

```sh
make seed     # carga seed/seed.jsonl (si existe) y lo indexa
# o
make ingest   # recolecta lo tuyo; edita antes config/sources.yaml
make index    # trocea + embeddings + FTS5
```

## Cómo funciona

Tres capas separadas:

1. **Ingesta** (`radar/ingest.py`) — habla con Thordata, descarga crudo a
   `samples/raw/` y llena SQLite. Se ejecuta a mano. Nunca se vuelve a pedir un
   `video_id` ya guardado.
2. **Indexado** (`radar/index.py`) — trocea las transcripciones en fragmentos de
   60–90 s con 15 s de solape, genera embeddings (multilingües) por lotes y
   llena FTS5.
3. **API + UI** (`radar/app.py` + `frontend/`) — busca solo sobre lo local:
   BM25 de FTS5 + similitud coseno, fusionados con Reciprocal Rank Fusion. El
   LLM redacta con citas; si falla o se desactiva (`RADAR_NO_LLM=1`), la búsqueda
   sigue mostrando los fragmentos.

## Qué cuesta

Coste dominante: **Thordata, 1 crédito por resultado** (cada vídeo descargado
son ~2 resultados: metadatos + transcripción). El límite duro por ejecución se
configura con `MAX_REQUESTS_PER_RUN` y la ingesta pide confirmación antes de
gastar.

Los embeddings son baratos: en una ejecución real de prueba, indexar 2 vídeos /
3 fragmentos costó **1 petición de embeddings** (lote de 3 textos, dimensión
detectada 4096) y cada búsqueda con respuesta cuesta **1 embedding + 1 chat**.

## Estado

- El resultado de `youtube_transcript_by-id` está **confirmado**: es una lista de
  `{transcriptdownloadUrl, video_id, file_size, error, error_code}`. No trae la
  transcripción, trae el enlace a un `.txt` (`radar/parsers.py`).
- Falta el **formato interno de ese `.txt`** (y los ejemplos de
  `youtube_product_by-id` y del descubrimiento). Hasta entonces el parser avisa
  con un mensaje claro y no adivina la estructura.
- Los spiders de **descubrimiento** están marcados `SIN CONFIRMAR EN PANEL` y
  aislados en `radar/spiders.py`.
- El `seed/seed.jsonl` definitivo debe salir de una ejecución real de la ingesta.

## Tests

```sh
make test
```

## Licencia

MIT — ver [LICENSE](LICENSE).
