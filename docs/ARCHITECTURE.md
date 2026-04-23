# Architecture

## Overview
Проект реализован как `web + backend` прототип с поддержкой полного сценария кейса:
- отдельные роли (ученик, учитель, родитель),
- базовые процессы (задачи, статусы, напоминания, эскалации),
- ключевой AI-контур (извлечение задания, планирование, аналитика),
- надежный fallback для стабильного демо при недоступности Ollama.

## Backend
- `FastAPI` API слой.
- `SQLModel + SQLite` для персистентности.
- `TrackerService` как центральный application-сервис.
- `HybridAIService`:
  - primary: локальный `Ollama` (`/api/generate`),
  - fallback: deterministic-парсинг дедлайна/приоритета + rule-based планирование.

Основные сущности:
- `User`, `StudentTeacherLink`, `StudentParentLink`
- `Task`, `TaskStep`
- `ReminderRule`, `ReminderEvent`, `Notification`
- `Goal`, `PointEvent`
- `TeacherReview`, `HelpRequest`

## Frontend
- SPA на `React + TypeScript + Vite`.
- Роутинг по ролям:
  - `/login/student`, `/login/teacher`, `/login/parent`
  - `/dashboard/student`, `/dashboard/teacher`, `/dashboard/parent`
- Единая дизайн-система в стиле Neo-education:
  - выразительная типографика,
  - многоуровневый фон,
  - кастомные карточки,
  - плавные анимации появления,
  - адаптив desktop/mobile.

## AI Strategy
- Формат AI-ответов унифицирован (DTO-ориентированные ответы API).
- При ошибке Ollama backend автоматически переключается на fallback-логику без падения пользовательского сценария.
- Реализованы функции:
  - `extract_task` (предмет, дедлайн, приоритет),
  - `plan_task` (planned_at, interval_hours, steps),
  - `analytics` (сложные темы + рекомендации).

## Quality and Validation
- Unit-тесты:
  - дедлайны (`завтра`, `до пятницы`, дата без времени -> `23:59`),
  - приоритет (`срочно/важно`, близкий дедлайн).
- Интеграционный flow-тест:
  - создание,
  - напоминания и эскалации,
  - выполнение,
  - проверка учителя,
  - запрос/ответ помощи,
  - аналитика,
  - родительская лента.
