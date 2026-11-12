# Аудит проекта: AI Python Mentor

Дата аудита: 2026-11-10. Машина аудита: `instance-20261109-215044`, Ubuntu, kernel 7.0.0-1017-gcp,
4 vCPU, 15 GiB RAM, 39 GB свободно, пользователь `agent` (uid 1003, `CapEff: 0000000000000000`, sudo нет,
Docker не установлен).

Документ фиксирует только то, что проверено командой. Каждая строка дефекта содержит доказательство —
команду и её вывод. Статусы: `open`, `fixed`, `blocked` (нужен ресурс, которого нет на верстаке).

## 1. Как проверялось

```bash
# окружение
nproc; free -g; df -h /; docker version; unshare -Ur echo ok; cat /proc/self/status | grep CapEff

# API
cd apps/api && /home/agent/venvs/apm/bin/python -m pytest -q -p no:cacheprovider
cd apps/api && DATABASE_URL=postgresql+psycopg://mentor:mentor@127.0.0.1:55432/mentor \
  RUN_POSTGRES_TESTS=1 python -m pytest tests/test_postgres_specific.py -q

# миграции на PostgreSQL 16.15
alembic upgrade head
alembic downgrade 0036_content_completion && alembic upgrade head
alembic downgrade base && alembic upgrade head
alembic check

# бэкап и restore drill
bash scripts/backup.sh --database mentor --backup-dir /home/agent/backups
bash scripts/restore-drill.sh --bundle /home/agent/backups/<bundle>

# web
cd apps/web && npm ci && npm run lint && npm run build

# runner
python -m unittest discover -s apps/runner/tests
```

## 2. Сводка проверенного состояния

| Что | Результат | Команда |
|---|---|---|
| API-тесты (SQLite) | **363 passed, 10 skipped**, 351 s | `python -m pytest -q` |
| PostgreSQL-only тесты | **6 passed**, 3.85 s | `RUN_POSTGRES_TESTS=1 pytest tests/test_postgres_specific.py` |
| Миграции: 0037 → 0036 → 0037 | проходит, контрольные данные на месте | `alembic downgrade 0036_content_completion && alembic upgrade head` |
| Миграции: base → head | проходит, сид 90 навыков восстанавливается | `alembic downgrade base && alembic upgrade head` |
| `alembic check` | `No new upgrade operations detected.` | `alembic check` |
| Бэкап | 0.7 s, bundle с манифестом и sha256 | `scripts/backup.sh` |
| Restore drill | **passed**, 63 таблицы, row digests и revisions совпали, 3.2 s | `scripts/restore-drill.sh` |
| Web lint (`tsc --noEmit`) + build | зелёные, First Load JS 103 kB | `npm run lint && npm run build` |
| Runner-тесты | **32 passed**, 57 s (после закрытия P0-1) | `unittest discover -s apps/runner/tests` |
| TODO/FIXME в коде | 0 | `grep -rn "TODO\|FIXME" apps` |

Расхождение с постановкой: в мандате указано «~317 тестов». Фактически на `main` собирается
**373 теста** (363 passed + 10 skipped). Число 317 не подтверждается — в отчётах использую фактические.

## 3. Дефекты

### P0-1. Код ученика не исполнялся вообще (fail-closed на всех хостах) — `fixed`

Доказательство до исправления:

```bash
$ docker version
bash: docker: command not found
$ cat /proc/self/status | grep CapEff
CapEff:	0000000000000000
$ unshare -Ur echo ok
unshare: write failed /proc/self/uid_map: Operation not permitted
```

`apps/runner/runner_worker/policy.py` требует Docker + `runsc` + AppArmor-профиль + userns.
На верстаке нет ни root, ни Docker, ни user namespaces → `select_backend()` не мог выбрать ни один
бэкенд, любое задание отклонялось. Единственный бэкенд был недостижим, то есть исполнения не было.

Исправление: добавлен второй, непривилегированный бэкенд изоляции на Landlock LSM + seccomp-BPF +
rlimits (`apps/runner/runner_worker/sandbox_*.py`). Выбор бэкенда — `RUNNER_SANDBOX_BACKEND`
(`auto|docker|landlock`), `auto` предпочитает контейнер, если он есть, иначе падает на Landlock,
иначе отказ `no_sandbox_backend`. Подробности и обоснование — ADR в `docs/decisions.md`.

Доказательство после исправления:

```bash
$ python -m unittest apps.runner.tests.test_landlock_sandbox      # 15 тестов, escape-набор
$ python -m unittest apps.runner.tests.test_exercise_catalog      # 90 заданий, 288 кейсов
$ python -m unittest apps.runner.tests.test_server_mtls           # 8 тестов, живой mTLS-сервис
$ python -m unittest discover -s apps/runner/tests                # Ran 32 tests ... OK
```

### P0-2. Нет ни одного прогона 90 заданий через реальный исполнитель — `fixed`

Доказательство: до исправления в репозитории не было теста, который исполняет эталонные решения.
Добавлен `apps/runner/tests/test_exercise_catalog.py`: все 90 заданий, 288 кейсов (включая скрытые)
прогоняются через настоящий sandbox; эталонные решения дают 100%, starter code не даёт 100% ни в
одном задании.

```
Ran 3 tests in 41.262s
OK
```

### P0-3. AI Gateway без провайдера и без учёта стоимости — `fixed`

Было: адаптер без ключа, один вызов, без роутинга, ретраев и стоимости.

Стало: живой провайдер `https://ru.cheapvibecode.ru/v1` (48 моделей в каталоге), роутинг по тирам
`apps/api/config/model-routing.json` (fast/balanced/strong), цепочка моделей с 2 попытками и
экспоненциальным бэкоффом, переход на следующую модель при 429/5xx/таймауте, общий бюджет 45 с,
прогрев модели при старте, токены и стоимость в каждом вызове, дневной лимит
`AI_SPEND_DAILY_LIMIT_USD` (по умолчанию $5) с алертом на 80 %.

```
$ python ../../scripts/ai-smoke.py
ok task=tutor_chat lang=ru model=gpt-6-luna prompt=43 completion=37 cost=$0.000024 attempts=1 latency=3553ms
ok task=tutor_chat lang=en model=gpt-6-luna prompt=41 completion=35 cost=$0.000023 attempts=1 latency=8046ms
ok task=lesson_generation lang=ru model=gpt-6.1-sol ... latency=2739ms
ok task=lesson_generation lang=en model=gpt-6.1-sol ... latency=5370ms
RESULT: ok
```

Ключ живёт только в `.env` (не в git), в логах и ответах API его нет — проверено тестом
`test_every_call_is_logged_with_tokens_and_cost` (в записи журнала нет текста промпта).

### P1-1. PostgreSQL-набор фактически не запускался (на верстаке не было сервера) — `fixed`

На верстаке нет `psql` и root, поэтому PG-only тесты всегда скипались (`6 skipped`). Поднят
PostgreSQL 16.15 в пользовательском пространстве (conda-forge), миграции применены, тесты прогнаны: 6 passed.
В CI PG-набор есть, но локально он не воспроизводился.

### P1-2. Браузерный набор — `fixed`

Было: один сценарий. Стало после слияния #5/#6: 4 сценария × 2 вьюпорта = **8 тестов, 8 passed**
(новичок и его рабочее пространство, восстановление кода, синхронизация черновиков между
устройствами, изоляция чужого аккаунта). Прогон локальный с CI-паритетом: `CI=1`, свежая БД,
`seed-recovery.py`, Chromium 153.

Добавлен сквозной сценарий исполнения кода: `scripts/ui-smoke/execution.spec.mjs` проходит весь
путь браузер → API → очередь заданий → worker → mTLS runner → песочница → «Тесты: 3 из 3» и
«Обработка завершена». Прогон с `EXECUTION_E2E=1` при поднятой цепочке:

```
npx playwright test execution.spec.mjs --reporter=list
  ✓ [desktop] learner solution runs in the isolated runner and grades to 3 of 3 (7.7s)
  ✓ [mobile]  learner solution runs in the isolated runner and grades to 3 of 3 (6.7s)
  2 passed
```

Публикация проекта уже покрыта основным сценарием: форма портфолио, флаг `published`, переход по
публичной ссылке `/portfolio/<token>` и заголовок публичной страницы (снимок `23-public-portfolio`).
AI-чат проверяется в браузере в честном состоянии «не подключён», живой ответ — `scripts/ai-smoke.py`.

Осталось как отдельные сценарии: сброс пароля по письму (нужен SMTP) и живой AI-ответ в браузере
(нужен ключ в CI, стоимость на прогон).

```
$ npx playwright test --reporter=list
  8 passed (3.1m)
```

### P1-3. Мониторинг — `fixed`

Было: `grep -rln "prometheus|sentry|grafana"` даёт только `node_modules` и `.next` — метрик,
Sentry, дашбордов и алертов не было.

Стало: `/metrics` с латентностью, кодами по шаблону маршрута, токенами и стоимостью AI, отказами
по квотам, очередью executions и доступностью БД (`apps/api/app/metrics.py`); Sentry с очисткой
тела запроса, query string, `Authorization`, `Cookie` и `user` (`app/observability.py`);
Prometheus с 7 алертами (`ops/prometheus/alerts.yml`); Grafana с дашбордом на 10 панелей
(`ops/grafana/dashboards/apm.json`); структурные JSON-логи (`app/logging_config.py`).

```
$ python -m pytest tests/test_metrics.py tests/test_deploy_config.py -q
14 passed
```

### P1-4. Production-деплой — `partial` (артефакты готовы, живой прогон заблокирован)

Было: `ls compose.prod.yml` → файла нет; только dev-стек без runner, TLS и миграций на старте.

Стало: `compose.prod.yml` поднимает db → migrate → seed-check → api → workers → runner + reaper →
web → Caddy; профиль `monitoring` добавляет Prometheus и Grafana. Наружу публикует порты только
Caddy, `/metrics` и `/internal/*` закрыты. `docker compose up` на верстаке невозможен: нет Docker и
root — проверка структурная (8 тестов) плюс `docker compose config` на целевом хосте.

### P1-5. Runner в production-стеке — `fixed`

Добавлены `apps/runner/Dockerfile`, сервисы `runner` и `runner-reaper` в `compose.prod.yml`,
`.env.runner.example` без единого секрета приложения: тест
`test_runner_is_isolated_from_application_secrets` падает, если в окружении runner появится
`DATABASE_URL`, `AI_GATEWAY_API_KEY` или docker.sock.

### P2-1. LICENSE — `fixed`

Добавлен `LICENSE` (MIT, copyright 2026 coffee1337).

### P2-2. `docs/SPEC-MATRIX.md` — `fixed`

Матрица собрана: **250 строк**, done 68 / partial 126 / missing 35 / out-of-scope 21,
строк без статуса — 0. Каждая строка содержит код и тест или явное «нет».

### P2-3. Платёжный, email- и Telegram-контуры без боевых провайдеров — `open`

Адаптеры есть (`app/billing.py`, `app/notifications.py`), провайдеры не подключены, доставка не
проверялась. Решение по каждому — sandbox-прогон или ADR «вырезано».

### P3-1. PR #5 и #6 — `fixed`

Оба перебазированы на актуальный main, прогнаны на PostgreSQL и SQLite, влиты fast-forward,
ветки удалены, PR закрыты.

```
$ gh pr list --state open
open-prs: 0
```

#5: 289 API-тестов, 7 PG-тестов, web lint+build — зелено.
#6: миграции 0038–0039 проверены на копии PostgreSQL (upgrade → downgrade 0037 → upgrade,
контрольные данные сохранены, `alembic check` чист), 329 API-тестов, Playwright 8/8.

## 4. Что этот аудит не проверяет и почему

- **gVisor/runsc и cgroups v2.** На верстаке нет Docker и root, user namespaces запрещены
  (`unshare: write failed /proc/self/uid_map`). Контейнерный бэкенд остаётся в коде и выбран по
  умолчанию там, где Docker есть; проверить его здесь физически невозможно. Это граница, а не
  отговорка: непривилегированный бэкенд закрывает тот же контракт отказа (сеть, ФС, процессы,
  сигналы, CPU/RAM/время/вывод) и проверяется тестами на реальном ядре.
- **Реальная отправка email/платежей/Telegram.** Нет боевых аккаунтов.
- **Публичный TLS-домен и внешний ingress.** Верстак не публикуется наружу.

## 5. Итог текущего цикла

Закрыто с доказательствами: исполнение кода в изоляции (P0-1, P0-2), AI-контур на живом
провайдере (P0-3), PostgreSQL-набор и обратимость миграций (P1-1), браузерные сценарии и
исполнение кода в браузере (P1-2), наблюдаемость (P1-3), runner в production-стеке (P1-5),
LICENSE, SPEC-MATRIX, PR #5/#6, линтеры, CSP и ASVS-чеклист.

Остаётся: живой `docker compose up` и контейнерный бэкенд runner (нужен хост с Docker/runsc),
Sentry на фронтенде, публикация проекта как отдельный E2E-сценарий, 35 строк матрицы со статусом
`missing` (в основном P2: OAuth, PWA, streak, referral, admin UI) и открытые пункты ASVS
(HIBP-фид, абсолютный срок сессии, письма о неудачных входах).

## 6. Нестабильность верстака: спорадические SIGKILL дочерних процессов (2026-11-11)

При повторных прогонах каталога 90 заданий на верстаке часть дочерних процессов песочницы
стала завершаться сигналом 9 без вывода (`returncode = -9`, пустой stderr). Воспроизведено и
на пустом задании (`return solve(p): 1`), и при отключённых по отдельности rlimits, setsid и
seccomp-фильтре — 1–4 случая на 25 запусков. Обычные `python -c "print(1)"` в том же окружении:
0 из 60.

Проверка на чистом runner-е: GitHub Actions job «Runner isolation, policy and journal» гоняет
`unittest discover -s apps/runner/tests`, включая каталог 90 заданий и mTLS-сервис, и проходит
зелёным (runs 42946652594, 42949317178, 42953558113). Значит дефект не в коде песочницы, а в
окружении верстака (внешний reaper/супервизор процессов либо исчерпание ресурсов после многих
часов нагрузки). На верстаке каталог следует считать нестабильным индикатором, арбитр — CI.

Защита, которая осталась в коде независимо от причины: `_kill_group` не сигналит процесс,
который уже собран (`poll() is not None`), иначе SIGKILL мог попасть в переиспользованный pid
следующего задания.

## 7. P0-2. Контейнерный бэкенд был мёртвым кодом — `fixed` (W2)

До исправления `Policy.argv()` передавал `--security-opt apparmor=ai-tutor-runner`, а профиля с таким
именем в репозитории не было: `docker create` падал бы на любом хосте, поэтому контейнерный путь не
запускался ни разу. Ни один тест его не вызывал, а `Policy.sandbox()` для `backend="docker"` возвращал
`None`, то есть допуск и исполнение в контейнере не были покрыты вообще.

Что сделано и чем доказано:

| Проверка | Команда | Результат |
|---|---|---|
| Слои изоляции хоста | `python scripts/runner-docker-bootstrap.py --require-gvisor` | `{"apparmor": true, "cgroup2": true, "gvisor": true, "limits": true, "linux": true, "seccomp": true, "userns": false, "runtime": "runc"}` |
| Побеги и каталог в контейнере | CI job «Learner code in containers (gVisor and kernel parity)» | 31 тест, 150.996 s, зелёный |
| Каталог 90 заданий на gVisor | тот же job, `RUNNER_DOCKER_FULL=1` | 90 заданий / 288 кейсов, эталоны 100 % |
| Паритет бэкендов | `test_backends_agree_on_the_same_cases` | вердикты Landlock и контейнера совпали на 12 заданиях |

Побеги, которые теперь проверяются поведением, а не конфигом: чтение `/home/agent/.env`, `/etc/shadow`
и каталога, запись в `/app` и `/etc/cron.d`, сеть к `1.1.1.1:80`, утечка переменных окружения через
sentinel `APM_SECRET_SENTINEL`, бесконечный цикл, бомба памяти, флуд stderr, fork-бомба против
`--pids-limit 32`, запуск `/bin/sh`. Последний пункт потребовал правки образа: в `python:3.12-slim`
есть shell, поэтому из образа удалены `/bin/sh`, `/bin/dash`, `/bin/bash`, apt и dpkg.

Что осталось честной границей: AppArmor-профиль в CI не загружается (`Failed setting up policy cache:
Permission denied` — у hosted-раннера нет прав на `/var/cache/apparmor`), поэтому job идёт на слоях
`gVisor + seccomp + cgroups v2 + read-only + no-network`. Профиль лежит в
`apps/runner/deploy/apparmor-ai-tutor-runner` и грузится bootstrap-скриптом там, где ядро это позволяет.
Признак `apparmor` в `host-layers.json` берётся из `docker info`, а не из предположения.

## 8. Устаревшие числа в этом документе

Раздел 2 писался на первом прогоне и содержал `247 passed, 6 skipped`. Фактические числа на
`main` после закрытия P0-1 и P0-2: API — 363 passed, 10 skipped; PostgreSQL-only — 7 passed;
runner — 35 passed в unit-job'е и 13 контейнерных тестов в отдельном job'е. Числа обновлены здесь,
чтобы AUDIT, STATUS и SPEC-MATRIX не расходились.

## 9. W0. Красный main: четыре дефекта, все закрыты (2026-11-12)

Прогон 43193975454: **10 job'ов зелёные**, `COMPOSE SMOKE: ok`, API-набор `387 passed, 10 skipped`.
Ни один провал не был «инфраструктурой»: пять красных подряд дали четыре разных дефекта.

| # | Дефект | Доказательство до | Исправление |
|---|---|---|---|
| 1 | `alembic/env.py` вызывал `fileConfig` с дефолтным `disable_existing_loggers=True`; после теста миграций логгеры `mentor.request`, `ai.usage`, `runner.client` оставались выключенными | `test_the_log_line_repeats_the_id_and_never_the_payload`: `records.messages == []` в полном наборе, зелёный изолированно. Диагностика показала `disabled: True` у логгера | `disable_existing_loggers=False` + `conftest.py`, который падает на тесте-загрязнителе и называет логгер |
| 2 | Проверка заголовков в смоуке: `printf \| tr \| grep -q` под `pipefail` возвращала код SIGPIPE из `tr`, когда `grep -q` закрывал вход после совпадения | `FAIL missing header x-content-type-options` при реально присутствующем заголовке, рядом `tr: write error: Broken pipe` | проверки переписаны на `case` по заранее посчитанной строке, без пайплайнов |
| 3 | Клиентские сертификаты монтировались только в контейнер `api`; `execution-worker` вызывал раннер без PKI и падал до залогированного участка | задание получало `unavailable` с сообщением воркера, в логах воркера ноль строк | монтирование перенесено в общий якорь `x-api-common`; тест deploy-конфигурации требует PKI у любого сервиса с `RUNNER_*` |
| 4 | Тест fork-бомбы форкал детей, которые сразу выходили — 200 последовательных fork законны, pids-limit не проверялся | job «Learner code in containers» упал на коммите 5716287, был зелёным до него | дети живут 30 с, проверяется предел одновременных процессов |

Дополнительно раннер перестал молчать: `runner_execution_failed reason=<код>` и
`runner_admission_failed reason=<код>` — раньше любой `NotReady` и любое исключение
превращались в `worker_not_ready` без строки в логе.

Что доказано смоуком в проде-стеке (job «Production compose comes up and serves the journey»):

```
ok   register (201) / onboarding (200) / next lesson (200)
ok   public portfolio page (200) / portfolio api is public (200)
ok   runner is configured for the API
ok   job finished (finished)          ← код ученика реально исполнился
ok   metrics hidden (404) / internal runner path hidden (404)
ok   header strict-transport-security … referrer-policy / server banner hidden
ok   port 8443, 80, 443 published (proxy) / database is internal only
ok   webhook without secret (503) / api healthy after restart (200)
ok   session survives restart (200)
COMPOSE SMOKE: ok
```
