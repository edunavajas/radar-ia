#!/bin/sh
# Crea e inicializa /app/data y cede la propiedad al usuario del host para que
# un clon limpio funcione sin ficheros root en ./data.
set -e

DATA_DIR=/app/data
mkdir -p "$DATA_DIR"

if [ "$(id -u)" = "0" ]; then
    chown -R "${RADAR_UID:-1000}:${RADAR_GID:-1000}" "$DATA_DIR" 2>/dev/null || true
    exec gosu "${RADAR_UID:-1000}:${RADAR_GID:-1000}" "$@"
fi

exec "$@"
