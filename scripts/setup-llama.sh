#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-llama3.2:1b}"

echo "Проверяю Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Ollama не найден, устанавливаю через Homebrew..."
    brew install ollama
  else
    echo "Ollama не найден и Homebrew отсутствует. Установите Ollama вручную: https://ollama.com/download"
    exit 1
  fi
fi

if command -v brew >/dev/null 2>&1; then
  brew services start ollama >/dev/null 2>&1 || true
fi

if ! pgrep -f "ollama serve" >/dev/null 2>&1; then
  echo "Запускаю ollama serve..."
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
fi

echo "Жду готовности Ollama..."
for _ in {1..30}; do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! ollama list >/dev/null 2>&1; then
  echo "Ollama не отвечает. Проверьте /tmp/ollama-serve.log"
  exit 1
fi

echo "Подтягиваю модель ${MODEL} (может занять время)..."
ollama pull "${MODEL}"

echo "Проверяю, что модель отвечает..."
ollama run "${MODEL}" "Ответь одним словом: готово" | head -n 1

echo ""
echo "Готово. Для backend используйте:"
echo "  OLLAMA_MODEL=${MODEL}"
echo "  OLLAMA_BASE_URL=http://127.0.0.1:11434"
