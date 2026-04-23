#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8080}"

if command -v ssh >/dev/null 2>&1; then
  echo "Открываю публичный туннель через localhost.run для http://127.0.0.1:${PORT}"
  echo "После запуска появится ссылка вида: https://<id>.lhr.life"
  echo ""
  ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R "80:localhost:${PORT}" nokey@localhost.run
  exit 0
fi

if command -v npx >/dev/null 2>&1; then
  echo "SSH недоступен, переключаюсь на localtunnel..."
  npx --yes localtunnel --port "${PORT}"
  exit 0
fi

if command -v cloudflared >/dev/null 2>&1; then
  echo "SSH и npx недоступны, переключаюсь на Cloudflare Quick Tunnel..."
  cloudflared tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate
  exit 0
fi

echo "Не найден ни ssh, ни npx, ни cloudflared. Установите один из инструментов и повторите."
exit 1
