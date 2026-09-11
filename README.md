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
  sin que YouTube te bloquee. Es lo único de pago del sistema.
- El **descubrimiento** (RSS) y los **metadatos** (oEmbed) son gratis y no
  necesitan credenciales.

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
make ingest   # recolecta las fuentes de config/sources.yaml (gasta créditos)
make index    # trocea + embeddings + FTS5
```

`make ingest` pide confirmación antes de gastar. Para ver el plan y el gasto
previsto sin gastar nada:

```sh
python -m radar.ingest --live --dry-run
```

## Cómo funciona

### Fuentes: una por proveedor, detrás de la misma interfaz

- **Transcripciones — Thordata** (`youtube_transcript_by-id`, de pago, 1 crédito
  por vídeo). Es la única vía sin alternativa gratuita para conseguir
  transcripciones a escala sin que YouTube bloquee. Devuelve un enlace a un
  `.vtt` que se descarga, se parsea y se persiste en local.
- **Descubrimiento — RSS público de YouTube** (gratis, sin API key).
  `feeds/videos.xml` da los últimos ~15 vídeos de un canal con id, título y
  fecha. Si configuras un `@handle`, se resuelve a `channel_id` una vez y se
  cachea en la tabla `channels`.
- **Metadatos — oEmbed público de YouTube** (gratis, sin credenciales).
  Título, canal y miniatura. Duración, vistas y likes **no existen** por esta
  vía: se quedan vacíos y la UI no los pinta, nunca ceros inventados.

RSS y oEmbed van con caché en disco y medio segundo entre peticiones.

### Capas

1. **Ingesta** (`radar/ingest.py`) — descubre por RSS, enriquece por oEmbed y
   pide la transcripción a Thordata. Deduplica por `video_id` (nunca vuelve a
   pedir un vídeo ya guardado) y persiste todo en local al momento, porque los
   resultados de Thordata caducan. `--dry-run` enseña el gasto sin gastar.
2. **Indexado** (`radar/index.py`) — trocea en fragmentos de 60–90 s con 15 s de
   solape, genera embeddings por lotes y llena FTS5.
3. **API + UI** (`radar/app.py` + `frontend/`) — busca solo sobre lo local:
   BM25 de FTS5 + similitud coseno, fusionados con Reciprocal Rank Fusion. El
   LLM redacta con citas; si falla o se desactiva (`RADAR_NO_LLM=1`), la búsqueda
   sigue mostrando los fragmentos.

## Qué cuesta

Coste dominante: **Thordata, 1 crédito por resultado** (cada vídeo descargado
son ~2 resultados: metadatos + transcripción). Una tarea real de 1 vídeo tardó
~53 s y consumió 1 crédito. El límite duro por ejecución se configura con
`MAX_REQUESTS_PER_RUN` y la ingesta pide confirmación antes de gastar.

Los resultados de Thordata **caducan a los 30 días**, así que la ingesta
persiste todo en local al momento (`samples/raw/` + SQLite) y nunca da por hecho
que puede volver a pedirlo.

Los embeddings son baratos: en una ejecución real de prueba, indexar 2 vídeos /
3 fragmentos costó **1 petición de embeddings** (lote de 3 textos, dimensión
detectada 4096) y cada búsqueda con respuesta cuesta **1 embedding + 1 chat**.

## Estado

- **Transcripciones**: Thordata `youtube_transcript_by-id` funcionando. El
  parser WebVTT (`radar/parsers.py`) maneja cabecera, `NOTE`/`STYLE`/`REGION`,
  cue settings, etiquetas inline, timestamps por palabra y deduplica el solape.
- **Descubrimiento y metadatos**: los scrapers de Thordata están rotos por su
  lado (404/520 desde su propio panel), así que se usan RSS y oEmbed públicos.
  Todo está aislado en `radar/sources/` (un módulo por proveedor): si algún día
  los arreglan, se cambia la implementación y nada más.
- El `seed/seed.jsonl` se genera con `--write-seed` a partir de una ejecución
  real de la ingesta.

## Tests

```sh
make test
```

## Licencia

MIT — ver [LICENSE](LICENSE).
