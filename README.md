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

### Windows без Docker

Для локального запуска нужны **Python 3.12 и Node.js 22**. PostgreSQL необязателен: можно явно выбрать SQLite, которая хранит данные в файле `apps/api/mentor-local.db`.

Если нужные версии ещё не установлены, выполните в PowerShell:

```powershell
winget install --exact --id Python.Python.3.12 --source winget
winget install --exact --id OpenJS.NodeJS.22 --source winget
```

Затем закройте PowerShell и откройте заново. Если `winget` отсутствует, установите [Python 3.12 для Windows](https://www.python.org/downloads/release/python-31210/) и [Node.js 22](https://nodejs.org/en/download/archive/v22) через официальные установщики.

Из корня скачанного проекта запустите API:

```powershell
cd C:\ai_bot_ai-main
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-api.ps1 -UseSqlite
```

Скрипт проверит Python, создаст `apps/api/.venv`, установит `requirements.lock`, проверит соединение с выбранной базой, выполнит миграции и запустит API. Активация окружения и отдельная команда `alembic` не нужны. При любой ошибке следующий этап не запускается. Параметр `-ExecutionPolicy Bypass` относится только к запущенному процессу; настройки политики системы не изменяются.

В **другом окне PowerShell** запустите frontend:

```powershell
cd C:\ai_bot_ai-main
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-web.ps1
```

Откройте http://localhost:3000. API: http://127.0.0.1:8000/docs. Проверка готовности: http://127.0.0.1:8000/ready. Оба сервера доступны только с этого компьютера; `Ctrl+C` останавливает соответствующий сервер. Frontend обращается к API через `/api`, а proxy использует `127.0.0.1`, чтобы не зависеть от разрешения `localhost` в IPv6.

`-UseSqlite` — явный выбор отдельной файловой базы. Аккаунты и история из PostgreSQL остаются там и автоматически не переносятся. Повторный запуск сохраняет файл и аккаунты. Не удаляйте `mentor-local.db`, если хотите сохранить прогресс; для резервной копии остановите API и скопируйте файл.

Для AI и других интеграций можно создать `.env` в корне по образцу `.env.example`. API читает его до миграций; переменные текущего процесса имеют приоритет. Секреты из этого файла не загружаются скриптом frontend. Без настроенного AI Gateway обучение по авторским материалам работает, AI-чат показывает недоступность. Исполнение кода требует отдельно развёрнутого защищённого Runner и при обычном локальном запуске отключено.

Если хотите использовать **свою установленную службу PostgreSQL**, задайте её `DATABASE_URL` в корневом `.env` или в текущем PowerShell и запустите API **без** `-UseSqlite`:

```powershell
cd C:\ai_bot_ai-main
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-api.ps1
```

При недоступном PostgreSQL скрипт остановится и предложит проверить `DATABASE_URL`, службу (`Get-Service *postgres*`) и порт. Автоматического перехода на другую базу нет. Не используйте этот launcher для production: он рассчитан на локальную разработку и HTTP; `APP_ENV=production` отклоняется.

Дополнительные параметры: `-SkipInstall` пропускает установку уже установленных зависимостей; `-PrepareOnly` проверяет окружение и выполняет подготовку без запуска сервера. У API есть `-PythonPath 'C:\путь\к\python.exe'`, если Python 3.12 не находится через launcher/PATH. Неполное окружение или `.venv` другой версии сохраняется: переименуйте его и повторите запуск, чтобы создать новое.

### Linux/macOS без Docker

Требуются Python 3.12, Node.js 22 и установленный PostgreSQL либо явный выбор SQLite:

```sh
cd apps/api
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python ../../scripts/local-api.py --use-sqlite
```

Без `--use-sqlite` используется `DATABASE_URL` из окружения или корневого `.env`. В другом терминале из `apps/web`: `npm ci`, затем `API_INTERNAL_URL=http://127.0.0.1:8000 NEXT_PUBLIC_API_URL=/api npm run dev`.

### Docker Compose

Этот способ запуска независим от нативного; PostgreSQL здесь запускается отдельным сервисом.

```sh
cp .env.example .env
# Задайте свой POSTGRES_PASSWORD в .env.
docker compose build
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up -d api web
```

Web: http://localhost:3000. API: http://localhost:8000/docs. `/health` проверяет соединение с БД; `/ready` дополнительно требует актуальную ревизию схемы. Frontend использует `/api` через Next.js proxy, поэтому удалённый браузер не обращается к своему localhost. Миграции запускаются явно. `docker compose down` сохраняет volume БД; `down -v` удаляет данные.

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

Браузерный CI проверяет путь новичка и основные экраны при 1440×900 и 390×844: восстановление шага/ответов, прогресс и повторения, поиск, сохранение карьерной цели, редактирование отправленных материалов и безопасное восстановление кода, keyboard focus в мобильном меню. Снимки страниц и отчёт доступны в артефакте `browser-ui-desktop-mobile`. Дополнительная QA-зависимость Playwright изолирована в `scripts/ui-smoke`; в bundle приложения она не попадает.

После входа dashboard показывает «На сегодня»; в меню есть «Мой прогресс» (`/learning/progress`), «Повторения» (`/learning/reviews`) и «История занятий» (`/learning/sessions`). Прогресс за 7/30 дней показывает записанные события и отдельно самостоятельные, assisted и retention observations. Поиск программы курса не открывает заблокированные уроки. В проектах можно просмотреть прежнюю отправку и скопировать её в новый черновик; принятие разделов не означает правильность кода. В истории попыток можно вернуть код точной версии текущего упражнения с резервным черновиком.

Шаг урока, неотправленные варианты ответа, код, объяснения и материалы этапов сохраняются в аккаунте. При изменении с двух устройств интерфейс показывает оба варианта и требует явного выбора; предыдущий вариант сохраняется локально перед заменой. При недоступной сети текст остаётся в редакторе и локальном черновике, если browser storage доступен. Выход очищает локальные копии; серверные черновики остаются в аккаунте. Удаление аккаунта удаляет их; удаление проекта удаляет черновики его этапов.

Таймер занятия сохраняет план на момент начала, паузы и время. Скрытие вкладки отправляет паузу; без подтверждения активности сервер ограничивает дальнейший отсчёт одной минутой. Продолжение требует явного действия, а завершение таймера не добавляет освоения темы. [Контракты синхронизации и занятий](docs/study-workspaces.md).

Windows CI отдельно проверяет нативные launcher-ы под **Windows PowerShell 5.1**: отсутствие Python, неполное окружение и реальный Python 3.11, ошибки pip/npm, недоступный PostgreSQL без fallback, отказ в production, миграции SQLite в каталоге с пробелами, реальный запуск API и Next.js, регистрацию через `/api`, cookie-сессию и сохранение аккаунта при повторной подготовке. Docker в этом job не используется. Локально на Windows проверку можно повторить командой `py -3.12 scripts/check-windows-startup.py`; она использует временную тестовую базу и порты 8000/3000, поэтому сначала остановите локальные серверы.

Из корня: `python -m unittest discover -s apps/runner/tests -v`. CI отдельно выполняет PostgreSQL migration round trip с sentinel-данными, `alembic check`, PG-specific tests, API tests, frontend types/build и worker policy/journal tests. Оркестрационные тесты worker не подтверждают фактическую изоляцию deployment host.

RAG: из `apps/api` команда `python -m app.knowledge_base` строит локальный индекс опубликованных immutable snapshots; для платного embedding rebuild используйте явный флаг из `--help`. Существующие learner-bound версии не переписываются.

[Backup и restore drill](docs/backup.md). [Статус и границы реализации](UNIMPLEMENTED_STAGES.md). Проектные инструкции находятся в `AGENTS.md`, `.agents/skills/`, `.codex/agents/`; полная исходная спецификация — `ai_programming_tutor_full_spec.md`.
