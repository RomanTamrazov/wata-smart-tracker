# WATA Smart Tracker v3

Веб-платформа для кейса WATA:
- роли `ученик / учитель / родитель`,
- классы и выдача ДЗ (классу или точечно),
- ИИ-извлечение задания (текст + фото/OCR),
- сдача решения (текст/голос/файлы),
- ИИ-помощь учителю при проверке,
- родительские цели и поощрения,
- Telegram-бот с синхронизацией задач.

## Быстрый запуск (локально, рекомендовано)

```bash
cd ../wata-smart-tracker
cp .env.example .env
./scripts/run-site.sh 8080
```

Сайт откроется по адресу:
- `http://127.0.0.1:8080`
- `http://<IP_вашего_компьютера>:8080` (для телефона в той же Wi‑Fi сети)

## Запуск Telegram-бота

1. В `.env` задайте `TELEGRAM_BOT_TOKEN=...`
2. Для кнопок перехода бот ↔ сайт укажите:
   - `PUBLIC_WEB_URL=https://ваш-публичный-домен`
   - `VITE_TELEGRAM_BOT_URL=https://t.me/<username_бота>` или `VITE_TELEGRAM_BOT_USERNAME=<username_бота>`
3. Запустите:

```bash
cd ../wata-smart-tracker
./scripts/run-bot.sh 8080
```

## Публичная ссылка для тестирования

```bash
cd ../wata-smart-tracker
./scripts/publish-site.sh 8080
```

Скрипт поднимет сайт и откроет внешний туннель.

## Ollama и OCR

Ollama (по желанию, для «живых» ИИ-ответов):
```bash
ollama pull llama3.2:1b
```

`run-site.sh` сам проверяет `ollama serve` и подтягивает модель при необходимости.

OCR (для извлечения текста с фото):
```bash
brew install tesseract tesseract-lang
```

## Docker-запуск (альтернатива)

```bash
cd ../wata-smart-tracker
cp .env.example .env
docker compose up --build -d
```

## Где хранятся данные

- База данных: `../wata-smart-tracker/backend/wata_tracker_v2.db`
- Загруженные файлы: `../wata-smart-tracker/backend/storage/uploads`

## Полная очистка данных

```bash
cd ../wata-smart-tracker/backend
rm -f wata_tracker_v2.db
rm -rf storage/uploads/*
```

После этого просто снова запустите `./scripts/run-site.sh 8080`.

## Проверка проекта

Backend:
```bash
cd ../wata-smart-tracker/backend
source .venv/bin/activate
pytest -q
```

Frontend:
```bash
cd ../wata-smart-tracker/frontend
npm run lint
npm run build
```
