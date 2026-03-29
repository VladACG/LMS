# Техническое задание LMS (MVP)

## 1. Область реализации
В рамках MVP реализуются только:
- Форма создания программы обучения.
- Структура модулей и уроков (видео, текст, тест).
- Создание группы и зачисление слушателей.
- Личный список уроков слушателя с обязательным порядком прохождения.
- Таблица слушателей с прогрессом.

Авторизация/регистрация/разграничение доступа по пользователям не реализуются.

## 2. Функциональные требования

### 2.1 Методист
- Создать программу: `name`, `description`.
- Добавить модуль в программу: `title`, `order_index`.
- Добавить урок в модуль:
  - `title`
  - `type` (`video` | `text` | `test`)
  - `content`:
    - для `video`: `video_url`
    - для `text`: `text_body`
    - для `test`: `questions_json`
  - `order_index`
- Просмотреть дерево программы (программа -> модули -> уроки).

### 2.2 Администратор
- Создать группу: `name`, `program_id`.
- Зачислить слушателей в группу:
  - вручную по строкам `full_name`, `email` (email опционален),
  - массово через textarea (по одной записи на строку).
- Получить таблицу прогресса группы.

### 2.3 Слушатель
- Выбрать себя из списка зачисленных (без логина).
- Получить список уроков своей группы в порядке:
  - доступен только первый не завершённый урок,
  - последующие уроки заблокированы.
- Отметить урок как завершённый.

### 2.4 Преподаватель и Куратор
- В MVP: read-only просмотр структуры программы и таблицы прогресса.

## 3. Нефункциональные требования
- Время ответа API (P95): до 300 мс на чтение, до 500 мс на запись при 100 RPS (load-smoke).
- Доступность локального окружения: запуск одной командой `docker compose up`.
- Логирование запросов: request_id, method, path, status, latency_ms.
- Валидация входных данных на backend и frontend.
- Идемпотентность операции завершения урока (повторный submit не ломает прогресс).

## 4. Модель данных

## 4.1 Таблицы
- `programs`
  - `id` UUID PK
  - `name` varchar(255) not null
  - `description` text null
  - `created_at` timestamptz
- `modules`
  - `id` UUID PK
  - `program_id` FK -> programs.id
  - `title` varchar(255)
  - `order_index` int
- `lessons`
  - `id` UUID PK
  - `module_id` FK -> modules.id
  - `title` varchar(255)
  - `type` enum(video,text,test)
  - `content_json` jsonb
  - `order_index` int
- `groups`
  - `id` UUID PK
  - `name` varchar(255)
  - `program_id` FK -> programs.id
- `students`
  - `id` UUID PK
  - `full_name` varchar(255)
  - `email` varchar(255) null
- `enrollments`
  - `id` UUID PK
  - `group_id` FK -> groups.id
  - `student_id` FK -> students.id
  - unique(group_id, student_id)
  - `enrolled_at` timestamptz
- `lesson_progress`
  - `id` UUID PK
  - `enrollment_id` FK -> enrollments.id
  - `lesson_id` FK -> lessons.id
  - unique(enrollment_id, lesson_id)
  - `status` enum(not_started,in_progress,completed)
  - `completed_at` timestamptz null
  - `score` numeric(5,2) null

## 4.2 Правило порядка
Глобальный порядок уроков считается через `(module.order_index, lesson.order_index)`. Завершить урок N можно только если уроки < N уже завершены.

## 5. API (MVP)

## 5.1 Программы и контент
- `POST /api/programs`
- `GET /api/programs`
- `GET /api/programs/{program_id}`
- `POST /api/programs/{program_id}/modules`
- `POST /api/modules/{module_id}/lessons`

## 5.2 Группы и зачисление
- `POST /api/groups`
- `GET /api/groups`
- `POST /api/groups/{group_id}/enrollments`
- `GET /api/groups/{group_id}/progress`

## 5.3 Траектория слушателя
- `GET /api/students/{student_id}/lessons?group_id=...`
- `POST /api/students/{student_id}/lessons/{lesson_id}/complete?group_id=...`

## 5.4 Ошибки и коды
- `400` валидация
- `404` сущность не найдена
- `409` нарушение порядка уроков / дубликат зачисления
- `422` ошибка бизнес-валидации

## 6. Требования к frontend
- SPA с 3 основными экранами:
  - Экран Методиста: форма программы и древовидный список модулей/уроков.
  - Экран Администратора: форма группы, зачисление слушателей, таблица прогресса.
  - Экран Слушателя: список уроков с блокировкой по порядку и кнопкой завершения.
- Обязательные состояния UI:
  - loading
  - empty
  - error
  - success
- В таблице прогресса обязательные колонки:
  - ФИО
  - Группа
  - Программа
  - Завершено уроков
  - Всего уроков
  - Прогресс (%)
  - Последняя активность

## 7. Развёртывание

## 7.1 Локально
- `docker compose up --build`
- Сервисы:
  - `frontend` (порт 5173 или 80)
  - `backend` (порт 8000)
  - `postgres` (порт 5432)

## 7.2 Сервер
- VM Linux + Docker Engine + Docker Compose Plugin.
- Reverse proxy: Nginx -> frontend/static и proxy на backend API.
- Бэкапы PostgreSQL: ежедневный dump + retention 7 дней.

## 8. Мониторинг и логирование
- Backend health-check: `GET /health`.
- Метрики: RPS, latency p50/p95, error rate.
- Логи в JSON-формате; корреляция через `request_id`.

## 9. Критерии приёмки
- Создание программы, модулей и уроков работает end-to-end.
- Группа создаётся и связывается с программой.
- Слушатели зачисляются; дубликаты отбрасываются корректно.
- Порядок прохождения уроков технически enforced.
- Прогресс корректно агрегируется и отображается в таблице.
- Покрытие backend unit+integration тестами не ниже 80% критических модулей.
- E2E happy-path и негативные сценарии проходят.
- Нагрузочный smoke (100 RPS, 5 мин) без критических ошибок.
