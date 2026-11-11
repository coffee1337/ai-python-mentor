# Статус проекта — 2026-11-11

Одна страница: где проект сейчас, что зелёное, что нет, что дальше.

## Зелёное (проверено командами)

| Область | Проверка | Результат |
|---|---|---|
| API, SQLite-набор | `cd apps/api && python -m pytest -q` | 329 passed, 10 skipped |
| API, PostgreSQL 16.15 | `RUN_POSTGRES_TESTS=1 pytest tests/test_postgres_specific.py` | 7 passed |
| Миграции | `alembic upgrade head` / `downgrade 0037` / `upgrade head` на копии PG | обратимы, данные сохраняются |
| Схема vs модели | `alembic check` | `No new upgrade operations detected.` |
| Бэкап | `bash scripts/backup.sh` | 0.7 s, манифест + sha256 |
| Restore drill | `bash scripts/restore-drill.sh --bundle …` | passed, 63 таблицы, digests совпали, 3.2 s |
| Web | `npm run lint && npm run build` | зелёные, First Load JS 103 kB |
| Runner | `python -m unittest discover -s apps/runner/tests` | 32 passed |
| Исполнение кода | `test_exercise_catalog` | 90 заданий, 288 кейсов, эталоны 100 % |
| Изоляция | `test_landlock_sandbox` | 15 тестов: `.env`, запись вне job, сеть, fork, exec, сигнал, CPU/RAM/вывод — отклонены |
| mTLS-сервис | `test_server_mtls` | 8 тестов: допуск, идемпотентность, чужой токен, клиент без сертификата |
| AI-контур | `scripts/ai-smoke.py` | 4 живых вызова RU+EN, 3–8 c, токены и стоимость в логах |
| AI-роутинг и лимиты | `tests/test_model_routing.py` | 12 passed |
| Метрики и Sentry | `tests/test_metrics.py` | 6 passed |
| Деплой-конфигурация | `tests/test_deploy_config.py` | 8 passed (сервисы, healthcheck, порты, секреты) |
| E2E браузер | `npx playwright test` (desktop+mobile) | 8 passed |
| Чистота | `grep -rn "TODO\|FIXME" apps` | 0 |

## Не зелёное

| Пункт DoD | Состояние | Что нужно |
|---|---|---|
| `docker compose up` на чистом хосте | конфигурация готова, прогон невозможен | верстак без Docker и root → нужен целевой хост |
| Контейнерный бэкенд runner (runsc + cgroups v2) | код есть, проверен unit-тестами | хост с Docker и runsc |
| Email / Telegram / платежи | адаптеры без провайдеров | боевые аккаунты владельца или ADR «вырезано» |
| E2E: исполнение кода и публикация проекта | не покрыто браузерным тестом | сценарий с поднятым runner-ом в стенде |
| OWASP ASVS-2 чеклист | не пройден формально | проход по пунктам с доказательствами |
| `ruff` | конфигурации нет | добавить конфиг и починить код |
| 35 missing из SPEC-MATRIX | не реализованы (в основном P2: OAuth, PWA, streak, referral, admin UI) | по приоритету |

## Ближайшие шаги

1. `ruff` конфиг + чистка (гейт «Линтеры чистые»).
2. E2E-сценарий исполнения кода с живым runner-ом.
3. OWASP ASVS-2: чеклист с доказательствами по auth/сессиям/загрузкам/промпт-инъекциям.
4. Email/Telegram/billing: sandbox-провайдер или ADR «вырезано» + чистка UI.
5. Прод-прогон `compose.prod.yml` на хосте владельца, затем тег v1.0.0.
