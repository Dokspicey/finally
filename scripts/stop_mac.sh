#!/usr/bin/env bash
# Stop and remove the FinAlly container (macOS / Linux).
# The host `db/` directory is left untouched so SQLite state persists.

set -euo pipefail

CONTAINER_NAME="finally"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Stopping $CONTAINER_NAME..."
  docker rm -f "$CONTAINER_NAME" >/dev/null
  echo "Stopped."
else
  echo "No $CONTAINER_NAME container is running."
fi
