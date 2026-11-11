# Runbook: деплой, откат, восстановление, алерты

Проверено на верстаке: миграции, бэкап, restore drill, тесты, сборка.
Не проверено здесь: `docker compose up` и выдача TLS-сертификата — на верстаке нет Docker и root.
Всё, что помечено **[host]**, выполняется на целевом хосте.

## 1. Что нужно от владельца

| Ресурс | Зачем | Без него |
|---|---|---|
| Домен + A-запись на IP хоста | Caddy выпускает TLS | `DOMAIN` не задан → стек не стартует |
| Email для ACME | Let's Encrypt | работает, но без уведомлений об истечении |
| `AI_GATEWAY_API_KEY` | живой AI-контур | наставник отвечает 503, остальное работает |
| SMTP-провайдер | подтверждение email, сброс пароля | регистрация без письма: смотри ADR в `docs/decisions.md` |
| Платёжный провайдер | подписки | billing UI скрыт, лимиты по тарифу free |
| `SENTRY_DSN` и `NEXT_PUBLIC_SENTRY_DSN` | ошибки backend и frontend | ошибки только в JSON-логах; фронт собирается без трекера |
| `GRAFANA_ADMIN_PASSWORD` | дашборды | профиль `monitoring` не стартует |

## 2. Первый деплой [host]

```bash
# 1. Код и окружение
git clone https://github.com/coffee1337/ai-python-mentor.git /opt/mentor && cd /opt/mentor
cp .env.prod.example .env.prod && $EDITOR .env.prod      # пароли, домен, ключи
# 2. PKI для runner (mTLS) — генерируется один раз, приватные ключи не в git
PYTHONPATH=apps/api python scripts/runner-dev-bootstrap.py /etc/ai-tutor
# 3. Каталог заданий (содержит hidden-тесты: права 0600, только для runner)
PYTHONPATH=apps/api python scripts/export-runner-catalog.py /etc/ai-tutor/catalog.json
cp /etc/ai-tutor/{ca,server,client}.pem /etc/ai-tutor/{server,client}.key /etc/ai-tutor-keys/  # см. ниже
# 4. .env.runner
cp .env.runner.example .env.runner && $EDITOR .env.runner   # token, пути, backend
# 5. Подъём
docker compose -f compose.prod.yml --env-file .env.prod up -d --build
docker compose -f compose.prod.yml ps
curl -fsS https://$DOMAIN/health
```

Порядок старта задан зависимостями: `db` → `migrate` → `seed-check` → `api` → остальные.
`seed-check` падает, если в базе меньше 90 навыков или 90 заданий: пустой курс не поедет.

Проверка после деплоя:

```bash
curl -fsS https://$DOMAIN/ready                       # {"status":"ready"}
curl -fsS https://$DOMAIN/metrics | head             # 404: метрики наружу закрыты
docker compose -f compose.prod.yml exec api python -m app.seed_check
```

## 3. Обновление версии

```bash
cd /opt/mentor && git fetch --tags && git checkout v1.0.0
docker compose -f compose.prod.yml --env-file .env.prod up -d --build
docker compose -f compose.prod.yml logs --tail=100 migrate seed-check
```

Миграции применяет отдельный one-shot сервис `migrate`; API стартует только после успеха.
Downgrade автоматически не выполняется — см. раздел 5.

## 4. Откат релиза

```bash
git checkout <предыдущий-тег>
docker compose -f compose.prod.yml --env-file .env.prod up -d --build
```

Если предыдущая версия несовместима со схемой (миграция необратима в данных), откат идёт
через восстановление бэкапа (раздел 5), а не через downgrade на живых данных.

## 5. Бэкап и восстановление

Бэкап (ежедневно, cron/systemd timer):

```bash
cd /opt/mentor && set -a && . .env.prod && set +a
PGHOST=db PGPORT=5432 PGUSER=$POSTGRES_USER PGDATABASE=$POSTGRES_DB \
  PG_BIN=/usr/lib/postgresql/17/bin BACKUP_ENCRYPTED_STORAGE=1 \
  bash scripts/backup.sh --database $POSTGRES_DB --backup-dir /var/backups/mentor
```

Restore drill (неразрушающий: создаёт `mentor_restore_*`, сверяет counts и row digests):

```bash
cd /opt/mentor && set -a && . .env.prod && set +a
PGHOST=db PGPORT=5432 PGUSER=mentor_restore PGPASSFILE=/etc/mentor/pgpass \
  DRILL_ADMIN_USER=mentor_admin DRILL_ADMIN_PASSFILE=/etc/mentor/pgpass \
  PG_BIN=/usr/lib/postgresql/17/bin BACKUP_ENCRYPTED_STORAGE=1 \
  bash scripts/restore-drill.sh --bundle /var/backups/mentor/<bundle>
```

Измерено на верстаке (PostgreSQL 16.15, 63 таблицы): бэкап **0.7 с**, restore drill **3.2 с**,
counts, row digests, колонки и ревизии совпали. **RPO = интервал бэкапа (24 ч), RTO ≈ 4 мин**
(restore + `migrate` + старт API).

Полное восстановление (авария):

```bash
docker compose -f compose.prod.yml stop api execution-worker notification-worker web
docker compose -f compose.prod.yml exec db psql -U $POSTGRES_USER -d postgres \
  -c "CREATE DATABASE mentor_new TEMPLATE template0"
docker compose -f compose.prod.yml exec -T db pg_restore -U $POSTGRES_USER -d mentor_new \
  --no-owner --no-privileges < /var/backups/mentor/<bundle>/database.dump
# переключение: остановить, переименовать БД, поднять
docker compose -f compose.prod.yml up -d
```

## 6. Алерты и реакция

| Алерт | Что значит | Первое действие |
|---|---|---|
| `ApiDown` | `/metrics` недоступен 2 мин | `docker compose ps`, `logs api` |
| `DatabaseDown` | healthcheck БД внутри API падает | `docker compose logs db`, место на диске |
| `HighErrorRate` | >5% 5xx за 5 мин | `logs api` по `request_failed`, Sentry |
| `SlowApi` | P95 > 2 c за 10 мин | очередь, медленные запросы в трейсах, БД |
| `AiSpendHigh` | >$4 за час | проверить `apm_ai_spend_micro_usd_total`, лимит `AI_SPEND_DAILY_LIMIT_USD` |
| `AiQuotaRejections` | >20 отказов за 15 мин | тарифы, `AI_DAILY_CALL_LIMIT`, всплеск трафика |
| `ExecutionQueueBacklog` | >25 заданий в очереди 10 мин | `logs execution-worker`, жив ли `runner` |
| `AiGatewayErrors` | >25% ошибок AI | провайдер, fallback-цепочка в `model-routing.json` |

## 7. Runner: два бэкенда

- `RUNNER_SANDBOX_BACKEND=docker` — прод-профиль: нужен хост с Docker, `runsc`, cgroups v2,
  AppArmor-профиль `ai-tutor-runner` и смонтированный runtime socket. Проверяется self-attestation
  при приёме задания; несоответствие — отказ, а не деградация.
- `RUNNER_SANDBOX_BACKEND=landlock` — хост без root: Landlock LSM + seccomp + rlimits.
  Self-attestation прогоняет 7 атак (чтение `.env`, запись вне каталога задания, TCP, fork, exec,
  сигнал чужому процессу) и требует отказа по каждой.
- `auto` выбирает docker, если он пригоден, иначе landlock, иначе отказ `no_sandbox_backend`.

Проверка на хосте:

```bash
docker compose -f compose.prod.yml exec runner python - <<'PY'
from runner_worker.policy import select_backend
print("backend:", select_backend())
PY
curl -fsS "https://$DOMAIN/internal/v1/runner/executions" || echo "внутренний API наружу закрыт — ок"
```

## 8. Ротация секретов

```bash
# токен runner
openssl rand -hex 32   # → RUNNER_AUTH_TOKEN в .env.prod и .env.runner
docker compose -f compose.prod.yml up -d api execution-worker runner
```

Ключ AI-шлюза меняется только в `.env.prod` + `up -d api`: маршрутизация моделей остаётся в
`apps/api/config/model-routing.json`.
