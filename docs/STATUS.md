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

## Состояние на 2026-11-12 (после закрытия missing)

- SPEC-MATRIX: **done 97, partial 125, missing 0, out-of-scope 28** из 250.
- API-тесты: 459 passed, 10 skipped (локально, полный прогон 461 с), Python 3.12 в CI — зелёный.
- CI: 11 job'ов зелёные (run 43251326953), включая gVisor-контейнер, compose-стек,
  браузерные сценарии и Windows-startup.
- Миграции: 0046 — голова; `alembic check` без дрейфа, round trip 0001 → head → 0046.

Закрыто в этом раунде: интересы как обёртка примеров (14.2), объяснение решения в
портфолио (15.4), версии промптов со стабильным сплитом (21.3), бенчмарк AI 24.1–24.3,
ограничения мобильного редактора (28.3), алерт расхода владельцу (32.3), стадии задания
и latency (103–106.1).

Вырезано осознанно, с ADR: OAuth (6.2, 53.3), импорт репозиториев (33.6), симулятор
интервью (76.1), рефералка (80.1), второй язык контента (81.2), Redis (34.2 — до замеров W5).

## Ближайшие шаги

1. W3 — SMTP-контур в CI (MailHog), закрытие ASVS 2.2.3.
2. W5 — нагрузка 100–200 VU: три числа (до/после), порог для ADR по Redis.
3. W1 — 125 partial: каждый либо доказательство, либо ADR.
4. Релиз — тег v1.0.0 только после внешних критериев (почта, бот, платежи, прод-хост).
