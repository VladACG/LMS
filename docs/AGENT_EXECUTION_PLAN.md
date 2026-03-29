# План работы агентов и контроль качества

## 1. Команда агентов
- Агент 1 (Backend): проектирование БД, API, бизнес-правила порядка уроков.
- Агент 2 (Frontend): SPA-интерфейсы Методиста/Администратора/Слушателя.
- Агент 3 (QA/Test): тест-стратегия, автотесты, нагрузочное тестирование, quality gates.

## 2. Матрица ответственности (RACI)
- Модель данных и миграции: R=Агент 1, A=Тимлид, C=Агент 3
- API-контракт: R=Агент 1, A=Тимлид, C=Агент 2/3
- UI и UX потоков: R=Агент 2, A=Тимлид, C=Агент 1/3
- Автотесты backend: R=Агент 3, C=Агент 1
- Автотесты frontend/e2e: R=Агент 3, C=Агент 2
- Load tests: R=Агент 3, C=Агент 1

## 3. План спринта (локальная фаза)

### Этап 0. Инициализация
- Агент 1: поднимает backend skeleton + миграции.
- Агент 2: поднимает frontend skeleton + маршруты экранов.
- Агент 3: настраивает тестовый контур (pytest/vitest/playwright/k6).

Quality gate после этапа:
- backend unit smoke = pass
- frontend unit smoke = pass
- health-check API = pass
- load sanity (20 RPS, 1 мин) = pass

### Этап 1. Контент программы
- Агент 1: endpoints программ/модулей/уроков.
- Агент 2: форма создания программы и контент-дерево.
- Агент 3: API tests + UI component tests.

Quality gate после этапа:
- API tests по контенту = pass
- UI tests формы = pass
- load read/write smoke (50 RPS, 2 мин) = pass

### Этап 2. Группы и зачисление
- Агент 1: endpoints групп и enrollments.
- Агент 2: формы группы и зачисления.
- Агент 3: интеграционные тесты и негативные кейсы (дубликаты/невалидные id).

Quality gate после этапа:
- integration tests = pass
- e2e admin flow = pass
- load create/list (75 RPS, 3 мин) = pass

### Этап 3. Траектория слушателя и прогресс
- Агент 1: правила порядка + агрегатор прогресса.
- Агент 2: экран слушателя и таблица прогресса.
- Агент 3: e2e student flow + race-condition checks.

Quality gate после этапа:
- e2e happy/negative = pass
- regression suite = pass
- load mixed scenario (100 RPS, 5 мин) = pass

## 4. Definition of Done (на задачу)
- Код и тесты в одном PR.
- Линтеры/форматтеры зелёные.
- Обновлена документация API/UI при изменении контракта.
- Есть минимум один негативный тест для бизнес-ограничений.
- Для изменений в критических endpoint добавлен/обновлён load-check.

## 5. Минимальный набор автотестов
- Backend unit:
  - сортировка и порядок уроков
  - запрет завершения урока вне очереди
  - агрегирование прогресса
- Backend integration:
  - сценарий program -> module -> lesson -> group -> enrollment -> progress
- Frontend unit:
  - валидация форм
  - корректное отображение состояний (loading/empty/error)
- E2E:
  - методист создаёт контент
  - администратор создаёт группу и зачисляет
  - слушатель проходит уроки по порядку

## 6. Нагрузочное тестирование (обязательно после каждого этапа)
- Инструмент: k6.
- Профили:
  - sanity: 20 RPS, 1 мин
  - smoke: 50-100 RPS, 2-5 мин
  - spike: +200% RPS на 30 секунд
- SLA пороги:
  - error_rate < 1%
  - p95 < 500ms (write), < 300ms (read)
  - p99 < 900ms

## 7. CI пайплайн
1. `lint`
2. `backend-unit`
3. `frontend-unit`
4. `integration`
5. `e2e`
6. `load-smoke`
7. `build-images`

Переход к деплою на сервер разрешён только при полном green pipeline.
