#!/usr/bin/env bash
# Start the FinAlly container (macOS / Linux).
#
# Usage:
#   scripts/start_mac.sh           # build image if missing, then run
#   scripts/start_mac.sh --build   # force rebuild before run
#
# Idempotent: removes any existing `finally` container before starting a new one.

set -euo pipefail

IMAGE_NAME="finally:latest"
CONTAINER_NAME="finally"
PORT="${FINALLY_PORT:-8000}"

# Resolve repo root from this script's location so the script works from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

FORCE_BUILD=0
for arg in "$@"; do
  case "$arg" in
    --build) FORCE_BUILD=1 ;;
    -h|--help)
      sed -n '2,7p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "Error: .env not found at $REPO_ROOT/.env." >&2
  echo "Copy .env.example to .env and fill in your keys." >&2
  exit 1
fi

mkdir -p "$REPO_ROOT/db"

image_exists() {
  docker image inspect "$IMAGE_NAME" >/dev/null 2>&1
}

if [ "$FORCE_BUILD" -eq 1 ] || ! image_exists; then
  echo "Building image $IMAGE_NAME..."
  docker build -t "$IMAGE_NAME" "$REPO_ROOT"
fi

# Remove any prior container (running or stopped) so this script is idempotent.
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Removing existing container $CONTAINER_NAME..."
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "Starting $CONTAINER_NAME on port $PORT..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -v "$REPO_ROOT/db:/app/db" \
  -p "$PORT:8000" \
  --env-file "$REPO_ROOT/.env" \
  "$IMAGE_NAME" >/dev/null

echo
echo "FinAlly is starting at: http://localhost:$PORT"
echo "Health check:           http://localhost:$PORT/api/health"
echo "Logs:                   docker logs -f $CONTAINER_NAME"
echo "Stop:                   scripts/stop_mac.sh"
