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

En un clon limpio, tal cual:

```sh
cp .env.example .env    # rellena THORDATA_TOKEN, AI_API_BASE_URL y AI_API_KEY
docker compose up
```

Abre http://localhost:8000. La base de datos se crea sola en `./data` la primera
vez.

Para ver la app con contenido, carga el seed incluido y genera sus embeddings:

```sh
make seed
```

`make seed` es el paso normal para tener la app funcionando sin gastar créditos.
Para recolectar contenido propio (gasta créditos de Thordata):

```sh
make ingest   # usa config/sources.yaml; pide confirmación antes de gastar
make index    # trocea + embeddings + FTS5
```

Variables del arranque:

- `RADAR_PORT` — puerto del host (por defecto `8000`). Ej.: `RADAR_PORT=8090 docker compose up`.
- `RADAR_UID` / `RADAR_GID` — a quién pertenece `./data` (por defecto `1000:1000`).

`data/` es local y **no viaja en el repo** (está en `.gitignore`): contiene la
base de datos, los vectores y las respuestas crudas. El contenedor la crea e
inicializa al arrancar y le da permisos del usuario del host, así que no quedan
ficheros de root.

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

RSS y oEmbed van con caché en disco y medio segundo entre peticiones. Todo vive
en `radar/sources/` (un módulo por proveedor): cambiar de proveedor es cambiar
una implementación y nada más.

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

Coste dominante: **Thordata, 1 crédito por transcripción**. El descubrimiento
(RSS) y los metadatos (oEmbed) son gratis. Los vídeos sin subtítulos no generan
resultado.

Ejecución real de `config/sources.yaml` (35 canales, últimos 7 días):

```
canales:               35
vídeos en ventana:     153
transcritos:           135   (en=72, es=45, ko=16, ja=1, zh=1)
sin subtítulos:         18
segmentos:             71.446
chunks:                2.296
créditos gastados:     135
tiempo total:          12m 12s  (8 workers; ~53 s por tarea)
```

Indexar esos 2.296 chunks son ~2.300 textos en embeddings por lotes con el
proveedor de IA. Los resultados de Thordata **caducan a los 30 días**, así que la
ingesta persiste todo en local al momento y nunca da por hecho que puede volver
a pedirlo.

## El corpus local

`data/` no se versiona. Para mover una base de datos ya construida entre
máquinas, empaqueta `data/` y descomprímela en la raíz del repo, de forma que
quede `./data`; el `docker compose up` la levantará con todo dentro.

## Tests

```sh
make test
```

## Licencia

MIT — ver [LICENSE](LICENSE).
