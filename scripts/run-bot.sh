#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8080}"

load_env_if_exists() {
  local env_path="$1"
  if [ -f "${env_path}" ]; then
    set -a
    source "${env_path}"
    set +a
  fi
}

load_env_if_exists "${ROOT_DIR}/.env"
load_env_if_exists "${ROOT_DIR}/backend/.env"
load_env_if_exists "${ROOT_DIR}/.env.local"
load_env_if_exists "${ROOT_DIR}/backend/.env.local"

if [ -z "${TELEGRAM_BACKEND_BASE:-}" ]; then
  export TELEGRAM_BACKEND_BASE="http://127.0.0.1:${PORT}/api/v1"
fi

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "Ошибка: TELEGRAM_BOT_TOKEN не найден в переменных окружения."
  echo "Проверьте один из файлов:"
  echo "  - ${ROOT_DIR}/.env"
  echo "  - ${ROOT_DIR}/backend/.env"
  echo ""
  echo "Пример строки:"
  echo "  TELEGRAM_BOT_TOKEN=123456789:AA...."
  exit 1
fi

cd "${ROOT_DIR}/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]"

echo "Запускаю Telegram-бот. Backend API: ${TELEGRAM_BACKEND_BASE}"
echo "Токен Telegram подхвачен (длина: ${#TELEGRAM_BOT_TOKEN})."
python -m app.services.telegram_bot
