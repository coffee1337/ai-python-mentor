# AI-наставник Python Backend

Next.js 15 / React 19, FastAPI, SQLAlchemy, Alembic и PostgreSQL. Модульный монолит для обучения Python → Python Backend.

## Возможности

- Cookie-сессии, Argon2, CSRF, onboarding, профиль и цель; подтверждение email, смена и одноразовый сброс пароля, отзыв сессий, экспорт и удаление аккаунта.
- Старт с нуля без обязательной диагностики: объяснение первой программы, построчный разбор, словарь и практика после изучения необходимых основ.
- 90 активных авторских уроков для всех 90 навыков, 3 backend-фазы, адаптивная диагностика, серверные quiz/knowledge checks, лестницы подсказок и отложенные повторения.
- Immutable content snapshots и append-only evidence; отдельные показатели знаний, практики, самостоятельности и retention. Порядок вариантов ответа стабилен внутри серверной сессии и меняется между сессиями.
- 90 отдельных Python-заданий `solve(payload)` с публичными примерами и закрытыми тестами. API сохраняет код и ставит задания в долговечную очередь; исполнение происходит на отдельном защищённом host.
- Письменные разборы с историей, авторские сигналы ошибок, детерминированный и AI-план; AI free-text feedback имеет рекомендательный статус и не начисляет mastery.
- AI Gateway, локальный RAG по точной версии урока, явный rebuild индекса, durable quotas/leases и учёт usage/стоимости.
- Анализ вставленного текста вакансии, требования с фрагментами источника, skill gaps, выбор целевой вакансии и перестройка плана.
- 9 шаблонов проектов, история milestone-артефактов и явная публикация портфолио. Комплектность артефакта отделена от проверки корректности кода.
- Тарифы/entitlements, подписанный webhook биллинга, настроенный checkout adapter; email/Telegram outbox, напоминания и краткий Telegram tutor; ограниченные административные операции с аудитом.

## Запуск

Требуются Docker Compose либо Python 3.12, Node 22 и PostgreSQL 17.

```sh
cp .env.example .env
# Задайте свой POSTGRES_PASSWORD в .env.
docker compose build
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up -d api web
```

Web: http://localhost:3000. API: http://localhost:8000/docs. `/health` проверяет соединение с БД; `/ready` дополнительно требует актуальную ревизию схемы. Frontend использует `/api` через Next.js proxy, поэтому удалённый браузер не обращается к своему localhost. Миграции запускаются явно. `docker compose down` сохраняет volume БД; `down -v` удаляет данные.

Для нативной разработки:

```sh
cd apps/api
python -m pip install -r requirements.lock
# Экспортируйте DATABASE_URL из вашего .env перед командой Alembic.
alembic upgrade head
uvicorn app.main:app --env-file ../../.env --reload
```

В другом терминале из `apps/web`: `npm ci && npm run dev`. `API_INTERNAL_URL` по умолчанию указывает на http://localhost:8000. Копирование `.env` само по себе не экспортирует переменные в shell.

## Настройка интеграций

Все поля находятся в `.env.example`; Compose передаёт их только backend-сервисам. В production задайте `APP_ENV=production`, HTTPS, `COOKIE_SECURE=true`, точный `WEB_ORIGINS` и секреты из deployment secret storage. Не публикуйте `.env`, приватные ключи или Runner-каталог.

- AI: `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL`, `AI_GATEWAY_API_KEY`. Без них детерминированное обучение работает, а AI возвращает явный unavailable. Лимиты тарифа и `AI_DAILY_CALL_LIMIT` применяются совместно. Денежный бюджет требует верхней резервации цены вызова; точная стоимость требует exact provider usage и deployment-owned цен для конкретной модели. Платный query embedding имеет отдельную квоту и ledger; без embedding usage стоимость остаётся оценочной. Operator CLI rebuild индекса — отдельная явно запускаемая операция, не запрос ученика.
- Email: HTTPS `EMAIL_DELIVERY_URL` / `EMAIL_DELIVERY_API_KEY`. Adapter принимает `{to,template,data}` и стабильный `Idempotency-Key`; account templates содержат одноразовый token/expiry. В разработке можно явно включить `DEV_ACCOUNT_TOKENS=true`; production никогда не возвращает эти токены клиенту.
- Telegram: bot token/username и webhook secret; webhook — `/webhooks/telegram`, secret передаётся в стандартном `X-Telegram-Bot-Api-Secret-Token`. Связь подтверждается одноразовым `/start <token>` в личном чате. Обычный текст после связи ставит ответ наставника в outbox; повтор update не создаёт повторный запрос.
- Уведомления: `docker compose --profile notifications up -d notification-dispatcher`. Без настроенного транспорта сообщения не отправляются. Транспортные повторы имеют семантику at-least-once; Telegram может повторить доставку после неопределённого сетевого исхода.
- Биллинг: HTTPS checkout service принимает `{user_id,plan_id}` и возвращает `{checkout_url}`; секрет сервиса хранится только backend. `/webhooks/billing` принимает строгий provider-neutral event с HMAC-SHA256 и timestamp; конкретный платёжный провайдер подключается adapter-ом. Без него оплата недоступна, платный тариф нельзя получить запросом из браузера. Цены не выдумываются.
- Admin: `ADMIN_USER_IDS` содержит точные UUID администраторов. `/admin/metrics`, `/admin/usage`, отзыв сессий и bounded enqueue/dispatch защищены сессией, а записи — дополнительно CSRF.

## Исполнение Python

[Развёртывание Runner](docs/runner-deployment.md), [протокол](docs/runner-protocol.md) и [условия безопасности](docs/runner-security-review.md). По умолчанию код сохраняется, но исполнение отключено. Для включения нужен отдельный проверенный Linux host, Docker cgroups v2 / runsc, pinned image, reviewed seccomp/AppArmor/user namespaces, mTLS и независимый reaper. Затем настройте API client certificates/policy через secret mounts, `RUNNER_*`, `EXECUTION_JOBS_ENABLED=true` и запустите `execution-dispatcher` с профилем `execution`.

Backend-упражнения моделируют отдельные правила чистыми функциями; они не разворачивают произвольный FastAPI/SQL/Redis-проект ученика. Проектные артефакты проверяются на комплектность, не исполняются. Эти ограничения отражены в API/UI.

## Проверки и эксплуатация

```sh
cd apps/api
python -m pytest -q
# На выделенной тестовой PostgreSQL БД:
RUN_POSTGRES_TESTS=1 python -m pytest -q tests/test_postgres_specific.py
alembic check
cd ../web
npm run lint
npm run build
```

Браузерный CI проверяет путь новичка и основные экраны при 1440×900 и 390×844. Снимки страниц и отчёт доступны в артефакте `browser-ui-desktop-mobile`. Дополнительная QA-зависимость Playwright изолирована в `scripts/ui-smoke`; в bundle приложения она не попадает.

Из корня: `python -m unittest discover -s apps/runner/tests -v`. CI отдельно выполняет PostgreSQL migration round trip с sentinel-данными, `alembic check`, PG-specific tests, API tests, frontend types/build и worker policy/journal tests. Оркестрационные тесты worker не подтверждают фактическую изоляцию deployment host.

RAG: из `apps/api` команда `python -m app.knowledge_base` строит локальный индекс опубликованных immutable snapshots; для платного embedding rebuild используйте явный флаг из `--help`. Существующие learner-bound версии не переписываются.

[Backup и restore drill](docs/backup.md). [Статус и границы реализации](UNIMPLEMENTED_STAGES.md). Проектные инструкции находятся в `AGENTS.md`, `.agents/skills/`, `.codex/agents/`; полная исходная спецификация — `ai_programming_tutor_full_spec.md`.
