#!/bin/bash
set -e

echo "=== Validating service ==="

MAX_RETRIES=10
RETRY_INTERVAL=6

for i in $(seq 1 $MAX_RETRIES); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/health || true)
  echo "  Attempt ${i}/${MAX_RETRIES}: HTTP ${STATUS}"

  if [ "$STATUS" = "200" ]; then
    echo "=== Service is healthy! ==="
    exit 0
  fi

  sleep $RETRY_INTERVAL
done

echo "=== ERROR: Service did not become healthy within $(( MAX_RETRIES * RETRY_INTERVAL )) seconds ==="
exit 1
