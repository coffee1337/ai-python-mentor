# Статус проекта — 2026-11-11 (второй заход)

Одна страница: 12 критериев готовности, что зелёное, что нет, что дальше.
Каждая строка подтверждена командой или CI-job'ом; чисел «на глаз» здесь нет.

## 12 критериев (мандат №2, раздел 1)

| # | Критерий | Статус | Доказательство |
|---|---|---|---|
| 1 | Трассируемость | частично | `docs/SPEC-MATRIX.md`: 250 строк — done 67, partial 127, missing 35, out-of-scope 21 |
| 2 | Исполнение кода | **зелёный** | CI job «Learner code in containers (gVisor and kernel parity)»: 31 тест, 150.996 s, зелёный; каталог 90 заданий / 288 кейсов на gVisor — эталоны 100 %; побеги в контейнере отклонены; паритет вердиктов с Landlock |
| 3 | AI-контур | зелёный | `scripts/ai-smoke.py`: живые вызовы RU+EN, токены и стоимость в логах; `tests/test_model_routing.py` 12 passed |
| 4 | **зелёный** | `test_security_headers.py` 4, `test_asvs_controls.py` 3, `test_email_delivery.py` 7; ASVS 2.2.3 закрыт письмом о неудачных входах |
| 5 | частично | email через SMTP и Telegram-бот работают (тесты на реальном SMTP-сокете и моке Bot API); платежи — ADR «вне v1.0», checkout скрыт |
| 6 | Тесты | зелёный | API 363 passed / 10 skipped, PG 7 passed, runner 35 passed + 13 контейнерных, E2E 8 + исполнение 2, k6 p95 76 ms |
| 7 | Наблюдаемость | частично | `/metrics`, Prometheus-правила и Grafana-дашборд валидированы `promtool` и `caddy validate`; агрегации логов (Loki) нет |
| 8 | Данные | зелёный | `alembic upgrade/downgrade/upgrade` на копии PG с контрольными данными; `alembic check` чистый; restore drill 63 таблицы |
| 9 | **зелёный** | CI job «Production compose comes up and serves the journey»: `COMPOSE SMOKE: ok`, включая исполнение кода через runner в compose-стеке (run 43193975454) |
| 10 | Красота | зелёный | `visual.spec.mjs`: 8 экранов × 360/768/1440, 6 passed; `tests/test_content_quality.py` 9 passed |
| 11 | Чистота | зелёный | `ruff check apps scripts` — All checks passed; TODO/FIXME — 0; тесты не отключены |
| 12 | нет | тег только v0.1.0, release notes не написаны (W9) |

## Зелёное (проверено командами)

| Область | Проверка | Результат |
|---|---|---|
| API, SQLite-набор | `cd apps/api && python -m pytest -q` | 387 passed, 10 skipped |
| API, PostgreSQL | `RUN_POSTGRES_TESTS=1 pytest tests/test_postgres_specific.py` | 7 passed |
| Runner, unit | `python -m unittest discover -s apps/runner/tests` | 35 passed, 13 skipped (контейнерные — отдельным job'ом) |
| Runner, контейнер | CI job «Learner code in containers» | 31 passed, каталог 90 заданий на gVisor |
| Изоляция ядра | `test_landlock_sandbox` | 15 тестов: `.env`, запись вне job, сеть, fork, exec, сигнал, CPU/RAM/вывод |
| Изоляция контейнера | `test_docker_backend` | 13 тестов: те же побеги + fork-бомба против pids-limit, sentinel окружения |
| mTLS-сервис | `test_server_mtls` | 8 тестов |
| Миграции | `alembic upgrade head` / `downgrade` / `upgrade` | обратимы, данные сохраняются |
| Бэкап и restore | `scripts/backup.sh`, `scripts/restore-drill.sh` | 0.7 s / passed, digests совпали |
| Web | `npm run lint && npm run build` | зелёные |
| E2E | `npx playwright test` | 8 passed; исполнение кода — 2 passed |
| Нагрузка | `k6 run scripts/load/learning.js` | p95 = 76 ms, 0 % ошибок |
| Ops-конфиги | `scripts/validate-ops.py` | promtool config + 8 правил, `caddy validate` — PASS |

## Не зелёное

| Пункт | Состояние | Что нужно |
|---|---|---|
| `compose.prod.yml` | конфигурация готова, прогон не выполнялся | CI-job compose smoke (W7) |
| Email | адаптер + outbox, доставки нет | MailHog/GreenMail в CI (W3), прод — SMTP от владельца |
| Telegram | вебхук-адаптер, бота нет | отдельный токен от владельца (W4), mock-сервер в CI |
| Платежи | `checkout_available=false` | sandbox-аккаунт или ADR «вне v1.0» (W6) |
| ASVS 2.2.3 | письма о неудачных входах не уходят | закрывается вместе с W3 |
| SPEC-MATRIX | 127 partial, 35 missing | W1: решение по каждой строке |
| Логи | структурированный JSON есть, агрегации нет | Loki или эквивалент (W7/W9) |

## Ближайшие шаги

1. W3 — SMTP-контур в CI (MailHog), закрытие ASVS 2.2.3.
2. W7 — `compose.prod.yml` поднимается в CI, smoke-набор, RUNBOOK по факту.
3. W4 — Telegram-бот продукта: привязка, `/today`, `/quiz`, отвязка, недельный отчёт.
4. W1 — матрица: partial → done или out-of-scope с ADR.
