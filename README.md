# LMS MVP

LMS-приложение с авторизацией и разграничением доступа по ролям:
`Слушатель`, `Преподаватель`, `Куратор`, `Методист`, `Администратор`, `Заказчик`.

## Что реализовано
- Вход по `email + пароль`.
- Обязательная смена временного пароля для слушателя при первом входе.
- Один пользователь может иметь несколько ролей одновременно.
- RBAC для API и интерфейса:
  - Слушатель: только свои группы/программы/прогресс/задания/оценки/вопросы.
  - Преподаватель: только назначенные группы + проверка заданий.
  - Куратор: свои слушатели, напоминания, ответы на вопросы, без оценивания.
  - Методист: создание/редактирование программ, без данных слушателей.
  - Администратор: пользователи, роли, группы, зачисление, назначения преподавателей/кураторов.
  - Заказчик: только прогресс своих сотрудников (read-only).
- Сохранены существующие фильтры и экспорт Excel для таблицы слушателей.
- Интеграции ступени 5:
  - Telegram: привязка аккаунта по invite-link + дублирование уведомлений.
  - Календарь: Google Calendar / Яндекс.Календарь / ICS для группы.
  - Хранилище файлов: материалы уроков и файлы заданий через storage backend (local/S3).
  - Платежи: платные программы, ссылка на оплату, webhook/mock подтверждение, блокировка доступа до оплаты.
  - Отчёты:
    - Админ: итоговый Excel по группе.
    - Заказчик: итоговый Excel по своим сотрудникам.
    - Методист: статистика по программе (API).
  - Журнал ошибок интеграций для администратора.

## Тестовые логины
- `admin@lms.local / Admin123!`
- `methodist@lms.local / Method123!`
- `teacher@lms.local / Teach123!`
- `curator@lms.local / Curator123!`
- `customer@lms.local / Customer123!`
- `student1@lms.local / Temp123!` (первый вход требует смену пароля)
- `student2@lms.local / Temp123!` (первый вход требует смену пароля)
- `multirole@lms.local / Multi123!` (teacher + curator)

## Структура
- `backend/` FastAPI + SQLAlchemy
- `frontend/` React + TypeScript
- `tests/load/` нагрузочные сценарии (`backend_smoke.py`, `k6_smoke.js`)
- `docs/` карта проекта и ТЗ

## Локальный запуск
1. Backend:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. Frontend (в новом терминале):
```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

3. Открыть `http://localhost:5173`.

## Проверки
- Полный прогон:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_all_checks.ps1
```

- k6 smoke (при запущенном backend):
```powershell
k6 run tests/load/k6_smoke.js --vus 5 --duration 20s --env BASE_URL=http://127.0.0.1:8000
```

## Docker
```powershell
docker compose build backend frontend
docker compose up -d
```
- Backend: `http://localhost:8000`
- Frontend: `http://localhost`

## Переменные окружения (интеграции)
`backend/.env` (или переменные среды):
- `APP_BASE_URL=http://localhost:8000`
- `TELEGRAM_BOT_TOKEN=...`
- `TELEGRAM_BOT_USERNAME=...`
- `STORAGE_BACKEND=local` или `s3`
- `STORAGE_LOCAL_PATH=./storage_data`
- `S3_ENDPOINT_URL=...`
- `S3_REGION=ru-central1`
- `S3_ACCESS_KEY_ID=...`
- `S3_SECRET_ACCESS_KEY=...`
- `S3_BUCKET_NAME=...`
- `YOOKASSA_SHOP_ID=...`
- `YOOKASSA_SECRET_KEY=...`
- `YOOKASSA_RETURN_URL=http://localhost:80`
