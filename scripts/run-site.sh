#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8080}"

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

if [ -z "${OLLAMA_BASE_URL:-}" ] || [ "${OLLAMA_BASE_URL}" = "http://host.docker.internal:11434" ]; then
  export OLLAMA_BASE_URL="http://127.0.0.1:11434"
fi

ensure_ollama_model() {
  local model="${OLLAMA_MODEL:-llama3.2:1b}"

  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama не найден. AI будет работать в fallback-режиме."
    return
  fi

  if ! pgrep -f "ollama serve" >/dev/null 2>&1; then
    echo "Запускаю ollama serve..."
    nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
    sleep 2
  fi

  if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fxq "${model}"; then
    echo "AI модель ${model} уже установлена."
    return
  fi

  if pgrep -f "ollama pull ${model}" >/dev/null 2>&1; then
    echo "AI модель ${model} уже загружается в фоне..."
  else
    echo "Запускаю загрузку AI модели ${model} в фоне (это может занять время)..."
    nohup ollama pull "${model}" >/tmp/wata-ollama-pull.log 2>&1 &
  fi

  echo "Пока модель не докачана, AI-ответы будут в fallback. Статус: tail -f /tmp/wata-ollama-pull.log"
}

LAN_IP=""
if command -v ipconfig >/dev/null 2>&1; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
  if [ -z "${LAN_IP}" ]; then
    LAN_IP="$(ipconfig getifaddr en1 2>/dev/null || true)"
  fi
fi

echo "Собираю frontend..."
ensure_ollama_model

cd "${ROOT_DIR}/frontend"
npm install
npm run build

echo "Поднимаю backend + frontend на одном домене через FastAPI..."
cd "${ROOT_DIR}/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]"

echo ""
echo "Сайт локально: http://127.0.0.1:${PORT}"
if [ -n "${LAN_IP}" ]; then
  echo "Сайт с телефона в той же Wi-Fi сети: http://${LAN_IP}:${PORT}"
else
  echo "Не удалось определить LAN IP автоматически. Проверьте IP вашей машины и используйте http://<IP>:${PORT}"
fi
echo "Для публичного доступа запустите в отдельном терминале: ./scripts/share-public.sh ${PORT}"
echo ""

FRONTEND_DIST_DIR="${ROOT_DIR}/frontend/dist" \
uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
