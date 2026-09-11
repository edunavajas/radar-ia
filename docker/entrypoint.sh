#!/bin/sh
# Prepara /app/data (bind mount) para cualquier uid del host: crea el directorio,
# lo deja escribible y evita que los ficheros nazcan solo para root.
# Es una app local de un usuario; no hay multi-tenant que aislar.
set -e

DATA_DIR=/app/data
mkdir -p "$DATA_DIR"
chmod 0777 "$DATA_DIR" 2>/dev/null || true
umask 000

exec "$@"
