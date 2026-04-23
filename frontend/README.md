# Frontend (WATA Smart Tracker)

SPA интерфейс для ролей:
- ученик,
- учитель,
- родитель.

## Запуск
```bash
cd /Users/roman/VScode/wata-smart-tracker/frontend
npm install
npm run dev
```

По умолчанию frontend ожидает backend на `http://127.0.0.1:8000`.

Если нужно изменить API, задайте переменную:
```bash
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1 npm run dev
```

## Сборка
```bash
npm run build
```
