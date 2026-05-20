#!/usr/bin/env bash
# Block until the e2e app container reports a healthy /api/health.
# Used by `npm run up` so Playwright never races the container.

set -euo pipefail

URL="${E2E_HEALTH_URL:-http://localhost:8001/api/health}"
TIMEOUT="${E2E_HEALTH_TIMEOUT:-60}"
DEADLINE=$(( $(date +%s) + TIMEOUT ))

echo "Waiting for $URL ..."
while true; do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    echo "App is healthy."
    exit 0
  fi
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "Timed out after ${TIMEOUT}s waiting for $URL" >&2
    docker compose -f "$(dirname "$0")/docker-compose.test.yml" logs --tail=80 app >&2 || true
    exit 1
  fi
  sleep 1
done
