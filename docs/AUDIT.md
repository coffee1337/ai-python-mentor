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
| API-тесты (SQLite) | **247 passed, 6 skipped**, 88 warnings, 797.99 s | `python -m pytest -q` |
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
**253 теста** (247 passed + 6 skipped). Число 317 не подтверждается — в отчётах использую фактические.

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

### P0-3. AI Gateway без провайдера и без учёта стоимости — `open`

`apps/api/app/ai_gateway.py` — адаптер; `AI_GATEWAY_URL`/`MODEL`/`API_KEY` не заполнены, реальных
вызовов нет. Ключ шлюза владельца (`CHEAPCODE_API_KEY`, `https://ru.cheapvibecode.ru/v1`) в репозитории
отсутствует и должен лежать только в `.env`.

### P1-1. PostgreSQL-набор фактически не запускался (на верстаке не было сервера) — `fixed`

На верстаке нет `psql` и root, поэтому PG-only тесты всегда скипались (`6 skipped`). Поднят
PostgreSQL 16.15 в пользовательском пространстве (conda-forge), миграции применены, тесты прогнаны: 6 passed.
В CI PG-набор есть, но локально он не воспроизводился.

### P1-2. Браузерный набор покрывает один сценарий — `open`

`scripts/ui-smoke/journey.spec.mjs` содержит **один** тест (`grep -c "test(" → 1`) на desktop+mobile.
В DoD требуются регистрация → урок → квиз → задача с исполнением → AI-чат → прогресс → публикация.
Отсутствуют: исполнение кода через runner, AI-чат, публикация проекта, восстановление пароля.

### P1-3. Мониторинга нет — `open`

`grep -rln "prometheus|sentry|grafana|opentelemetry"` по исходникам даёт только `node_modules` и
артефакты сборки `.next`; ни Prometheus-метрик, ни Sentry, ни дашбордов, ни алертов в коде нет.
`opentelemetry-api` есть в lock-файле, но не используется приложением.

### P1-4. Нет production-деплоя и `compose.prod.yml` — `open`

```bash
$ ls compose.prod.yml
ls: cannot access 'compose.prod.yml': No such file or directory
```

Есть только `docker-compose.yml` для разработки (db/api/web/execution-dispatcher). Нет runner-сервиса,
reverse-proxy с TLS, миграций на старте, идемпотентного сида.

### P1-5. Runner-сервис не входит в compose и не имеет production-упаковки — `open`

`apps/runner/deploy/` содержит systemd-юниты для отдельного хоста, но compose-профиля для runner нет.

### P2-1. LICENSE отсутствует — `open`

```bash
$ ls LICENSE*
ls: cannot access 'LICENSE*': No such file or directory
```

### P2-2. Нет `docs/SPEC-MATRIX.md` — `in progress`

Матрица трассируемости собирается отдельным проходом по спеке, README и UNIMPLEMENTED_STAGES.

### P2-3. Платёжный, email- и Telegram-контуры без боевых провайдеров — `open`

Адаптеры есть (`app/billing.py`, `app/notifications.py`), провайдеры не подключены, доставка не
проверялась. Решение по каждому — sandbox-прогон или ADR «вырезано».

### P3-1. PR #5 и #6 не слиты — `open`

```bash
$ gh pr list --state open
6  Sync private learning drafts across devices and track study sessions  codex/study-sync-sessions
5  Complete daily learning, progress and saved-work recovery            codex/study-workspace-completion
```

## 4. Что этот аудит не проверяет и почему

- **gVisor/runsc и cgroups v2.** На верстаке нет Docker и root, user namespaces запрещены
  (`unshare: write failed /proc/self/uid_map`). Контейнерный бэкенд остаётся в коде и выбран по
  умолчанию там, где Docker есть; проверить его здесь физически невозможно. Это граница, а не
  отговорка: непривилегированный бэкенд закрывает тот же контракт отказа (сеть, ФС, процессы,
  сигналы, CPU/RAM/время/вывод) и проверяется тестами на реальном ядре.
- **Реальная отправка email/платежей/Telegram.** Нет боевых аккаунтов.
- **Публичный TLS-домен и внешний ingress.** Верстак не публикуется наружу.
