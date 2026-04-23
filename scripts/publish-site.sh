#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8080}"
SITE_LOG="/tmp/wata-site.log"

cleanup_stale() {
  pkill -f -- "run-site.sh ${PORT}" >/dev/null 2>&1 || true
  pkill -f -- "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}" >/dev/null 2>&1 || true
  pkill -f -- "-R 80:localhost:${PORT} nokey@localhost.run" >/dev/null 2>&1 || true
  pkill -f -- "localtunnel --port ${PORT}" >/dev/null 2>&1 || true
}

cleanup() {
  if [ -n "${SITE_PID:-}" ] && kill -0 "${SITE_PID}" 2>/dev/null; then
    kill "${SITE_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "Очищаю старые процессы на порту ${PORT}"
cleanup_stale

echo "Запускаю сайт на порту ${PORT}"
"${ROOT_DIR}/scripts/run-site.sh" "${PORT}" >"${SITE_LOG}" 2>&1 &
SITE_PID=$!

echo "Жду готовности backend"
for _ in {1..120}; do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "Сайт не поднялся. Логи:"
  tail -n 80 "${SITE_LOG}" || true
  exit 1
fi

echo "Сайт поднят. Публичная публикация"
"${ROOT_DIR}/scripts/share-public.sh" "${PORT}"
