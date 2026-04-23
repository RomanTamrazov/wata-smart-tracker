# Пояснение По Файлам Проекта (RU)

Ниже перечислены рабочие файлы проекта, которые относятся к вашей разработке.

Не включены: `node_modules`, `dist`, `.venv`, `__pycache__`, `*.egg-info`, база `*.db`, загруженные пользовательские файлы в `storage/uploads`.

## Корень проекта

- `.env` — локальные переменные окружения: настройки Ollama, SMTP, OCR, Telegram, лимиты загрузок.
- `.gitignore` — исключения для Git (системные/временные файлы).
- `README.md` — основной быстрый запуск проекта и команды эксплуатации.
- `docker-compose.yml` — совместный запуск `frontend`, `backend` и `telegram-bot` в контейнерах.

## Документация

- `docs/ARCHITECTURE.md` — архитектурное описание backend/frontend/AI и базовых сценариев.

## Скрипты запуска и публикации

- `scripts/setup-llama.sh` — установка/проверка Ollama и загрузка модели.
- `scripts/run-site.sh` — сборка frontend + запуск FastAPI с раздачей SPA, вывод локального/LAN URL.
- `scripts/run-bot.sh` — запуск Telegram-бота с загрузкой env и проверкой токена.
- `scripts/share-public.sh` — открытие публичного туннеля (localhost.run/localtunnel/cloudflared).
- `scripts/publish-site.sh` — поднимает сайт и сразу публикует его через туннель.

## Backend (инфраструктура)

- `backend/.dockerignore` — исключения при сборке backend-образа.
- `backend/Dockerfile` — контейнер backend (Python, зависимости, tesseract, uvicorn).
- `backend/pyproject.toml` — зависимости и метаданные Python-пакета backend.

## Backend (приложение)

- `backend/app/__init__.py` — маркер Python-пакета backend.
- `backend/app/main.py` — создание FastAPI-приложения, CORS, lifespan, фоновый worker, раздача SPA.
- `backend/app/api.py` — REST-роуты `/api/v1/*`, привязка HTTP-слоя к `TrackerService`.
- `backend/app/config.py` — централизованные настройки из env (`Settings`).
- `backend/app/database.py` — создание движка SQLModel и SQLite-миграция/нормализация схемы.
- `backend/app/models.py` — SQLModel-модели домена (пользователи, классы, задания, проверки, цели, Telegram).
- `backend/app/schemas.py` — Pydantic-схемы запросов/ответов API.
- `backend/app/security.py` — хэширование паролей, соль, выпуск токенов сессии.
- `backend/app/utils.py` — время/таймзона (МСК), расчёт цвета срочности задачи.

## Backend (сервисы)

- `backend/app/services/tracker.py` — главный бизнес-сервис: регистрация, классы, задачи, выдача ДЗ, проверки, цели, Telegram-интеграция.
- `backend/app/services/ai_hybrid.py` — гибридный AI-контур: Ollama + fallback (извлечение, план, аналитика, чат, проверка).
- `backend/app/services/ai_fallback.py` — rule-based fallback логика для AI-сценариев.
- `backend/app/services/education_filter.py` — фильтрация неучебных заметок/задач.
- `backend/app/services/ocr.py` — OCR извлечение текста из фото через `pytesseract`.
- `backend/app/services/emailer.py` — SMTP-отправка писем и dry-run режим.
- `backend/app/services/uploads.py` — безопасное сохранение файлов, лимиты размера, очистка имени.
- `backend/app/services/reminder_worker.py` — фоновый цикл напоминаний и эскалаций.
- `backend/app/services/telegram_bot.py` — long-polling Telegram-бот, кнопки, вход, список задач, отметка выполнения.

## Frontend (инфраструктура)

- `frontend/.dockerignore` — исключения при сборке frontend-образа.
- `frontend/.gitignore` — исключения frontend-части.
- `frontend/Dockerfile` — сборка SPA и запуск через Nginx.
- `frontend/README.md` — локальный запуск frontend и переопределение API URL.
- `frontend/eslint.config.js` — правила линтинга TypeScript/React.
- `frontend/index.html` — HTML-шаблон точки входа SPA.
- `frontend/nginx.conf` — Nginx-конфиг: прокси API + SPA fallback.
- `frontend/package.json` — npm-скрипты и зависимости frontend.
- `frontend/package-lock.json` — lock-файл точных версий npm-зависимостей.
- `frontend/playwright.config.ts` — конфигурация e2e-тестов Playwright.
- `frontend/tsconfig.json` — корневой TypeScript-конфиг (references).
- `frontend/tsconfig.app.json` — TypeScript-конфиг клиентского приложения.
- `frontend/tsconfig.node.json` — TypeScript-конфиг для node-конфига Vite.
- `frontend/vite.config.ts` — конфиг Vite dev/build и proxy на backend.

## Frontend (статические ассеты)

- `frontend/public/favicon.svg` — favicon сайта.
- `frontend/public/icons.svg` — SVG-спрайт иконок.

## Frontend (код приложения)

- `frontend/src/main.tsx` — точка входа React, подключение Router и глобальных стилей.
- `frontend/src/App.tsx` — маршрутизация по ролям, shell, хранение сессии, подключение AI-виджета.
- `frontend/src/api.ts` — клиент API: запросы к backend, обработка ошибок/таймаутов, функции по всем сценариям.
- `frontend/src/types.ts` — общие типы frontend-моделей и API-ответов.
- `frontend/src/date.ts` — форматирование дат для UI и значений `datetime-local`.
- `frontend/src/labels.ts` — русские лейблы ролей/статусов/срочности.
- `frontend/src/styles.css` — дизайн-система и стили интерфейса.

## Frontend (компоненты)

- `frontend/src/components/LandingPage.tsx` — главная страница с ролями и CTA.
- `frontend/src/components/AuthPage.tsx` — вход/регистрация, валидация email и ФИО, выбор классов для ученика.
- `frontend/src/components/StudentDashboard.tsx` — кабинет ученика: задачи, фильтры, OCR/голос, сдача, классы, цели родителя.
- `frontend/src/components/TeacherDashboard.tsx` — кабинет учителя: классы/инвайты, выдача ДЗ, проверка с AI-подсказкой.
- `frontend/src/components/ParentDashboard.tsx` — кабинет родителя: лента сигналов, цели и поощрения.
- `frontend/src/components/AiAssistantWidget.tsx` — плавающий чат-виджет ИИ-ассистента.
- `frontend/src/components/ToastViewport.tsx` — всплывающие уведомления об успехе/ошибке.

## Тесты

- `frontend/tests/e2e/roles.spec.ts` — e2e-сценарии регистрации и базовых действий для ролей.

