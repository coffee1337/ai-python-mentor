# Статус проекта — 2026-11-10

Одна страница: где проект сейчас, что зелёное, что нет, что дальше.

## Зелёное (проверено командами)

| Область | Проверка | Результат |
|---|---|---|
| API, SQLite-набор | `cd apps/api && python -m pytest -q` | 247 passed, 6 skipped |
| API, PostgreSQL 16.15 | `RUN_POSTGRES_TESTS=1 pytest tests/test_postgres_specific.py` | 6 passed |
| Миграции | `alembic upgrade head` / `downgrade 0036` / `downgrade base` на PG 16 | обратимы, данные сохраняются |
| Схема vs модели | `alembic check` | `No new upgrade operations detected.` |
| Бэкап | `bash scripts/backup.sh` | 0.7 s, манифест + sha256 |
| Restore drill | `bash scripts/restore-drill.sh --bundle …` | passed, 63 таблицы, digests совпали |
| Web | `npm run lint && npm run build` | зелёные, First Load JS 103 kB |
| Runner | `python -m unittest discover -s apps/runner/tests` | 32 passed |
| Исполнение кода | `test_exercise_catalog` | 90 заданий, 288 кейсов, эталоны 100 % |
| Изоляция | `test_landlock_sandbox` | 15 тестов: чтение `.env`, запись вне job, сеть, fork, exec, сигнал, CPU/RAM/вывод — отклонены |
| mTLS-сервис | `test_server_mtls` | 8 тестов: допуск, идемпотентность, чужой токен, клиент без сертификата |
| Чистота | `grep -rn "TODO\|FIXME" apps` | 0 |

## Не зелёное

| Пункт DoD | Состояние | Что нужно |
|---|---|---|
| AI-контур на живом провайдере | адаптер без ключа/роутинга/стоимости | ключ шлюза в `.env`, `model-routing.json`, лимит $5/сутки |
| Регистрация/сброс/CSRF/rate limits | реализовано и покрыто тестами, OWASP ASVS-2 чеклист не пройден формально | проход по чеклисту с доказательствами |
| Email / Telegram / платежи | адаптеры без провайдеров | sandbox-провайдер или ADR «вырезано» |
| Playwright E2E | 1 сценарий (новичок, desktop+mobile) | сценарии исполнения кода, AI-чата, прогресса, публикации проекта |
| Наблюдаемость | нет | Prometheus, Grafana, логи, Sentry, алерты |
| `compose.prod.yml` | нет | API+web+worker+runner+PG+Redis+Caddy, миграции на старте, сид |
| LICENSE | нет | добавить |
| SPEC-MATRIX | в работе | матрица спека → код → тест |
| PR #5, #6 | открыты, #6 стоит на #5 | ревью, rebase, прогон на PG, merge |

## Ближайшие шаги

1. SPEC-MATRIX и закрытие расхождений по ней.
2. AI Gateway: список моделей, роутинг по тирам, ретраи, учёт токенов и стоимости, дневной лимит.
3. PR #5 → #6: rebase, PostgreSQL-прогон, merge.
4. Playwright: сценарии исполнения кода и AI-чата.
5. `compose.prod.yml` + Caddy + миграции на старте, затем деплой-прогон на чистой машине.
6. Наблюдаемость: метрики, дашборды, Sentry, алерты.
