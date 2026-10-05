# Набор агентов для AI-наставника

Скопируйте содержимое в корень репозитория. В наборе 13 Codex-агентов (`.codex/agents/`), 12 скиллов (`.agents/skills/`), проектный `AGENTS.md` и схема выбора моделей.

| Агент | Модель | Reasoning | Назначение |
|---|---|---|---|
| orchestrator | Muse Spark 1.3 (126% при 0,07) | high | Декомпозиция, выбор ролей, контроль бюджета |
| implementer | Grok 4.7 (124% при 0,5) | high | Бэкенд-фичи |
| frontend-implementer | Grok 4.7 (124% при 0,5) | high | Страницы, компоненты, формы, редактор кода |
| ui-designer | Muse Spark 1.3 | high | Визуальная система, состояния, доступность |
| api-designer | Grok 4.7 | high | Эндпоинты, контракты, схемы, миграции |
| content-author | Muse Spark 1.3 | high | Массовый контент курса, серии уроков |
| learning-content | Grok 4.7 | high | Один урок или набор с проверкой точности |
| tester | Muse Spark 1.3 | medium | Тесты и расследование падений |
| spec-tracer | Muse Spark 1.3 | high | Сверка спецификации с кодом, карта пробелов |
| reviewer | Grok 4.7 | xhigh | Независимое ревью diff |
| architect | GPT 6.1 Sol | high | Доменные решения и границы модулей |
| devops | GPT 6.1 Sol | high | Деплой, миграции, бэкапы, наблюдаемость |
| security-reviewer | GPT 6.1 Sol | xhigh | Sandbox, auth, PII, prompt injection |

Тринадцать агентов закрывают весь стек проекта: бэкенд, фронтенд, дизайн, контент, API, инфраструктура, аудит соответствия и безопасность.

Модели выбраны по соотношению качества и цены. Muse Spark 1.3 даёт 126% качества при коэффициенте 0,07 (эффективность ~1800 — лучшая в каталоге), Grok 4.7 — 124% при 0,5 (~248) против ~31 у GPT 5.6 Sol при том же классе качества. Массовые роли работают на дешёвых моделях; премиальные GPT остаются там, где вызовов единицы и цена ошибки высока: архитектура, инфраструктура и security.

Slug'ы сверены с каталогом провайдера (`cheapvibecode-models.json`) и записаны в формате `AI_GATEWAY_MODEL`. У Grok и DeepSeek контекст 500k против ~1M у GPT/Claude/GLM — на больших задачах учитывай это или режь входные chunks. Коэффициенты расходов относительные; сверяйте usage провайдера.
Оркестратор выбирает только нужные роли: маленькая правка — implementer; фича — implementer и целевой tester; доменная модель/миграция — architect, затем implementer/tester/reviewer; sandbox/auth/PII — security-reviewer. Дорогую модель включать по сигналам неоднозначности, двум неудачным попыткам или высокому риску. Не передавать весь проект и полную историю без необходимости.

Эти конфиги задают роли, но не включают автоматическую диспетчеризацию; основной Codex-агент должен делегировать им задачи. Установщик провайдера из второго файла скачивает каталог моделей; не редактируйте глобальный config/ключи ради этого набора.

---

# AI-наставник Python Backend

Next.js/React web, FastAPI API, PostgreSQL, SQLAlchemy и Alembic в структуре modular monolith. Доступны регистрация/вход, onboarding, профиль и авторский учебный маршрут.

## Требования

Эксплуатация БД: [резервное копирование PostgreSQL и restore drill](docs/backup.md).
В runbook есть отдельные команды для Linux и PowerShell, retention 7/4/6,
проверка `pg_restore -l`, Alembic и smoke `/health`/`/ready`. Backup хранится
только на зашифрованном выделенном диске; `$PGDATA` и Docker volume напрямую не
копируются.

- Docker Compose (рекомендуемый способ локального старта), либо Node.js 22+, Python 3.12+ и PostgreSQL 16+.

## Нативный PostgreSQL 17 на Windows (без Docker/WSL)

Эта последовательность устанавливает PostgreSQL 17 как Windows-службу, создаёт локальные
роль `mentor` и базу `mentor`, а также оставляет PostgreSQL доступным только через
`localhost`. `.env.example` не изменяется. Пароль роли вводится только интерактивно:
используйте значение `DATABASE_URL` из уже существующего локального `.env.example`,
но не добавляйте его в Git или в команды, сохранённые в файлах.

Откройте PowerShell **от имени администратора** и выполните:

```powershell
winget install --id PostgreSQL.PostgreSQL.17 --exact --source winget `
  --accept-source-agreements --accept-package-agreements

$Psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
$Createdb = "C:\Program Files\PostgreSQL\17\bin\createdb.exe"

# Введите пароль локальной административной роли postgres только в текущей сессии.
$env:PGPASSWORD = Read-Host "Пароль роли postgres"

$roleExists = (& $Psql -h localhost -U postgres -d postgres -tAc `
  "SELECT 1 FROM pg_roles WHERE rolname = 'mentor'").Trim()
if ($roleExists -ne "1") {
  & $Psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 `
    -c "CREATE ROLE mentor LOGIN"
} else {
  & $Psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 `
    -c "ALTER ROLE mentor LOGIN"
}

# Введите здесь пароль из локального DATABASE_URL в .env.example дважды.
& $Psql -h localhost -U postgres -d postgres -c "\password mentor"

$dbExists = (& $Psql -h localhost -U postgres -d postgres -tAc `
  "SELECT 1 FROM pg_database WHERE datname = 'mentor'").Trim()
if ($dbExists -ne "1") {
  & $Createdb -h localhost -U postgres -O mentor mentor
}
& $Psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 `
  -c "ALTER DATABASE mentor OWNER TO mentor"

# Не оставлять пароль администратора в окружении после настройки.
Remove-Item Env:PGPASSWORD

# Ограничить сетевое прослушивание localhost и применить настройку без перезагрузки ОС.
$env:PGPASSWORD = Read-Host "Пароль роли postgres"
& $Psql -h localhost -U postgres -d postgres -v ON_ERROR_STOP=1 `
  -c "ALTER SYSTEM SET listen_addresses = 'localhost'"
Set-Service -Name postgresql-x64-17 -StartupType Automatic
Restart-Service -Name postgresql-x64-17 -Force
Remove-Item Env:PGPASSWORD
```

Проверьте службу, версию и подключение. Последняя команда попросит пароль `mentor`;
он должен совпадать со значением, использованным в локальном `.env.example`:

```powershell
Get-Service postgresql-x64-17 | Select-Object Name,Status,StartType
& $Psql --version
& $Psql -h localhost -U mentor -d mentor -c `
  "SELECT current_user, current_database(), current_setting('server_version')"
Get-NetTCPConnection -LocalPort 5432 -State Listen |
  Select-Object LocalAddress,LocalPort
```

Ожидаемые значения: `Status=Running`, `StartType=Automatic`, PostgreSQL `17.x`,
пользователь/база `mentor`, и адреса прослушивания только `127.0.0.1` и `::1`.
После этого скопируйте `.env.example` в непубликуемый `.env`; значение
`DATABASE_URL` уже соответствует локальным `mentor`, `localhost:5432` и `mentor`.
Миграции запускаются отдельно из `apps/api`: `alembic upgrade head`. Этот раздел
не включает Docker Compose, WSL или Runner.

## Запуск всего стека

```sh
cp .env.example .env
docker compose build
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up -d api web
```

Затем откройте web: http://localhost:3000, API readiness: http://localhost:8000/health, Swagger: http://localhost:8000/docs. Для остановки: `docker compose down`. Данные базы сохраняются в volume `postgres_data`; `docker compose down -v` удалит их. Примерный пароль предназначен только для локальной разработки — задайте свой в `.env` и не используйте эти значения вне локальной среды.

Команды выше предназначены для Ubuntu с установленными Docker Engine и Compose plugin; выполняйте из корня проекта. Для существующей установки не перезаписывайте `.env`: начните с `docker compose build`. Миграции не запускаются автоматически. Ревизия `0003_learning` добавляет только таблицу завершений, сохраняя auth/onboarding. Откат этой ревизии (`docker compose run --rm api alembic downgrade 0002_auth_onboarding`) удалит только учебный прогресс; сначала сделайте резервную копию.

## Учебный маршрут

После входа и onboarding откройте dashboard → «Продолжить обучение» → `/learning`. Два небольших авторских урока (переменные, условия) содержат объяснение, пример и вопрос с выбором ответа. Верный ответ сохраняет завершение, открывает следующий урок; неверный позволяет повторить попытку. После последнего урока отображается конечное состояние. Прогресс сохраняется после перезагрузки/повторного входа и принадлежит пользователю текущей сессии.

API: `GET /learning/path`, `GET /learning/next` (возвращает `null` после завершения), `GET /learning/lessons/{id}`, `POST /learning/lessons/{id}/complete` с `{"answer":"6"}` и существующим CSRF-токеном. Все endpoints требуют сессию и завершённый onboarding. Клиент не передаёт user ID, статус завершения или оценку. Ответ-ключ не включается в lesson response; запись завершения уникальна по пользователю и lesson ID, а `exercise_version_id` фиксирует версию оценённого контента.

Это фиксированный стартовый маршрут, не адаптивная диагностика. `POST /learning/lessons/{id}/complete` сохраняет маркер в `LessonCompletion`: `authored_quiz_assisted`, если для урока уже есть сообщение assistant в mentor-чате, иначе `authored_quiz_correct`. Этот маркер не является `SkillEvidence` и сам по себе не калибрует mastery. Authored assessment и knowledge check теперь передают в `record_evidence` серверно выведенные `assisted`/`hint_count`: учитываются только distinct-уровни `HintReveal` того же пользователя, той же `ExerciseVersion` и не позже ответа/attempt; диапазон — 1–5, уровень 5 — solution. В уроке есть отдельная ladder подсказок: `POST /learning/exercises/{exercise_id}/hints` с JSON `{"level":1..5}`, `Idempotency-Key` и CSRF; раскрытие append-only, строго по одному следующему уровню, без answer keys в ответе. Lesson и knowledge-check flows привязаны к точной versioned lesson/exercise/check; публикация новой версии не переписывает старую. В уроке есть контекстный AI-чат с подсказками и наводящими вопросами, без исполнения пользовательского кода. Для включения задайте на сервере `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL` и `AI_GATEWAY_API_KEY`; endpoint должен принимать HTTPS POST с `{model,messages,max_completion_tokens}` и возвращать ровно один `choices[0].message.content` (Chat Completions-compatible). Пустая конфигурация отключает чат; ключ не попадает в web и не логируется. Изменение смысла урока/ответа требует нового versioned ID.

Проверки в Ubuntu Compose:

```sh
docker compose run --rm api python -m pytest -q -p no:cacheprovider
docker compose run --rm web npm run lint
docker compose build web
docker compose logs --tail=100 api web
```

Ручная проверка: завершить первый урок, обновить страницу, выйти/войти — второй урок остаётся следующим; у другого аккаунта маршрут начинается сначала. После двух верных ответов новых уроков нет.

## Запуск компонентов отдельно

Скопируйте `.env.example` в `.env` и запустите PostgreSQL: `docker compose up -d db`. Далее в терминале API установите зависимости `python -m venv .venv`, активируйте окружение и выполните `pip install -r apps/api/requirements.txt`; из каталога `apps/api` запустите `uvicorn app.main:app --reload`. Если API запущен на хосте, значение `DATABASE_URL` должно указывать на `localhost` (уже показано в `.env.example`).

Для web из `apps/web`: `npm install`, затем `npm run dev`.

## Проверки

### Быстрые проверки на SQLite

Из `apps/api` выполните `python -m pytest -q`. Текущий API-suite использует фикстуру `client` с SQLite `StaticPool`, поэтому это быстрый контур для API/домена. SQLite migration-тесты с временными базами и sentinel-данными также остаются быстрыми и не заменяют настоящий PostgreSQL; row locking и PostgreSQL-only ограничения проверяются отдельным PostgreSQL gate ниже.

### Явная проверка локального PostgreSQL 17

PostgreSQL 17 установлен локально и проверяется без Docker/Compose. Сначала задайте `DATABASE_URL` только в окружении текущего терминала, не печатая пароль, затем докажите фактически использованные dialect и базу:

```powershell
cd apps/api
$env:DATABASE_URL = "<локальное значение DATABASE_URL; пароль не печатать>"
python -c "from sqlalchemy import create_engine,text; import os; e=create_engine(os.environ['DATABASE_URL']); c=e.connect(); print('dialect='+c.dialect.name); print('driver='+c.dialect.driver); print('database='+str(c.execute(text('select current_database()')).scalar_one())); print('server_version='+str(c.execute(text('show server_version')).scalar_one()))"
```

После этого обязателен Alembic round trip с доказательством сохранности sentinel/счётчиков существующих данных:

```powershell
python -m alembic upgrade head
python -m alembic check
python -m alembic downgrade 0001_initial
python -m alembic upgrade head
```

На 4 октября 2026 года PostgreSQL `17.11` локально имеет состояние службы `Running/Automatic`; фактическое подключение подтверждено: `dialect=postgresql`, `driver=psycopg`, `database=mentor`. После исправления `0018_assessment_run_exercise_version` Alembic round trip пройден: `upgrade head`, `alembic check`, `downgrade 0001_initial` и повторный `upgrade head` завершились с exit 0.

PostgreSQL-only проверки теперь находятся в `apps/api/tests/test_postgres_specific.py`. Они намеренно не используют общую фикстуру `client`: обычный API-suite остаётся на SQLite. Файл пропускается без `RUN_POSTGRES_TESTS=1`, а `DATABASE_URL` задаётся явно в текущем терминале; переменная и пароль не печатаются. Запускайте файл отдельно из `apps/api`:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
$env:DATABASE_URL = "<локальное значение DATABASE_URL; пароль не печатать>"
python -m pytest -q -s tests/test_postgres_specific.py
```

Для отдельных проверок используйте их pytest node id:

```powershell
python -m pytest -q -s tests/test_postgres_specific.py::test_parallel_skill_evidence_updates_are_serialized
python -m pytest -q -s tests/test_postgres_specific.py::test_skill_evidence_idempotency_unique_constraint_rejects_duplicate
python -m pytest -q -s tests/test_postgres_specific.py::test_user_delete_cascades_learning_children
```

Ожидаемая строка доказательства содержит только фактические `dialect`, `driver` и `database` (например, `dialect=postgresql driver=psycopg database=mentor`), без `DATABASE_URL` и пароля. На 4 октября 2026 года запуск с `RUN_POSTGRES_TESTS=1` дал `3 passed`; без gate файл дал `3 skipped`. Это не переключает обычный API-suite с SQLite.

Непроверенными остаются только Runner и его изоляция, end-to-end браузер и Docker/Compose; CI не запускался.

## Контекстный AI-наставник

Миграция `0004_mentor_chat` добавляет `mentor_conversations` и `mentor_messages`.
Выполните `alembic upgrade head` перед запуском API. Откат до `0003_learning`
удаляет только историю чата; предварительно сохраните резервную копию.
Auth/onboarding не изменены.

Провайдер **не выбран**, модель по умолчанию отсутствует. Названия из
`model-routing.example.json` не являются runtime API IDs. В `.env` укажите
полный HTTPS URL Chat Completions endpoint, точный поддерживаемый model ID и ключ.
Compose передаёт эти переменные только API; при запуске API отдельно экспортируйте
их в окружение процесса (файл `.env` автоматически не загружается).
Не используйте `NEXT_PUBLIC_` для ключа.

Поддерживаемый явно настроенный контракт:
`POST AI_GATEWAY_URL`, `Authorization: Bearer AI_GATEWAY_API_KEY`,
JSON `{model, messages: [{role, content}], max_completion_tokens: 800}`.
Ожидается `choices: [{message: {role: "assistant", content: "..."}, finish_reason: "stop"}]`.
Выбирайте endpoint, документация которого подтверждает этот контракт; совместимость
конкретного vendor не предполагается и живой вызов не проверялся.
Gateway валидирует envelope через Pydantic, ограничивает ответ 64 KiB/12000 символами,
не следует redirects, не использует proxy из окружения, не возвращает тело ошибок
провайдера. Таймаут HTTP операций — 20 секунд, настройка 1–60 секунд.
Нет автоматических retries, fallback, tools или дополнительных модельных вызовов.

API: `GET /learning/lessons/{id}/chat` возвращает последние 50 сообщений владельца;
`before=<ISO datetime>` позволяет запросить предыдущую страницу.
`POST` туда же принимает `{"request_id":"<UUID>","message":"..."}` и CSRF.
История требует доступного урока и onboarding. Уникальная беседа принадлежит
текущему пользователю и версии урока. До 4000 символов, не более 5 попыток в минуту
на пользователя; ошибки тоже расходуют лимит. Повтор успешного request_id возвращает
сохранённый ответ без вызова модели; явный повтор неуспешного запроса делает один
новый вызов, не дублируя текст пользователя. При 502/504 текст сохраняется.
503 означает отсутствующую/невалидную конфигурацию; 429 — ограничение частоты.

Промпт `lesson_hint:v1` включает урок без answer key, уровень и до 6 последних
успешных сообщений. Пользовательский код не исполняется. Ответ выводится как текст,
не HTML. Ответ mentor-чата перед lesson quiz сохраняет `authored_quiz_assisted`
вместо `authored_quiz_correct` в `LessonCompletion`; сам chat не создаёт
`SkillEvidence`. Для assessment/knowledge check attribution учитывает recorded
`HintReveal`, не свободный текст mentor-чата.
Запрет полного решения в промпте не является гарантией поведения модели.
UI показывает последние 50 сообщений, ошибки и явный retry; старшие страницы
доступны через API. Нет token/cost billing, автоматического удаления истории или
адаптивной диагностики в этом этапе.

Следующие модули есть в коде; текущие SQLite/API-тесты подтверждают их поведение. Локальное подключение к PostgreSQL 17.11, фактические `dialect`/`driver`/`database`, Alembic round trip и PostgreSQL row locking подтверждены отдельными проверками; Runner/изоляция, browser E2E и Docker/Compose остаются непроверенными:

- Skill Graph (`0010`): модели, идемпотентный seed, API `/skills` и prerequisites двух уроков.
- SkillEvidence и SkillMasteryAudit (`0011`): `record_evidence` и server-derived hint attribution для assessment/knowledge check; assisted evidence привязано к пользователю, времени ответа и точной версии упражнения.
- Curriculum engine (`0012`) и AI curriculum (`0013`): gap/mastery/goal/prerequisites и сессии 20–60 минут есть; `vacancy_fit`, practice и review помечены `unavailable`.
- `AIUsageLedger` пишется AI curriculum и mentor chat: mentor записывает `mentor_chat` для успешных ответов, gateway errors и cache hits, с character counts и provider token fields только если они валидны. Это usage logging, а не полноценный billing: подписок, credits, budgets и alerts нет.

Token/cost billing по-прежнему нет. Python Runner остаётся fail-closed и возвращает `unavailable`; флага включения нет.

При конкурентных запросах PostgreSQL блокирует строку пользователя на время
ограниченного provider-вызова; это поведение подтверждено отдельным PostgreSQL-specific тестом. SQLite-тесты его не заменяют.
При аварийном завершении процесса между ответом провайдера и commit повтор может
снова вызвать модель: exactly-once доставка внешнего HTTP не гарантируется.

## Проверки и CI

Локально перед завершением задачи:

```bash
cd apps/api && python -m pytest -q
cd apps/web && npm run lint && npm run build
cd apps/api && alembic check
```

`npm run lint` — это `tsc --noEmit`, то есть только типы; визуальные и поведенческие дефекты он не ловит.

`.github/workflows/ci.yml` содержит отдельный job для round trip миграций на PostgreSQL 17 (`upgrade head` → `downgrade 0001_initial` → `upgrade head` → `alembic check`); CI здесь не запускался. Локально факт PostgreSQL подтверждён, а round trip и row locking прошли отдельную проверку.
## Coding practice

� Ubuntu: `cp .env.example .env && docker compose up --build` (����� ���������� Docker Compose plugin). ����� ��������� ��������: `docker compose exec api alembic upgrade head`. �������� `http://localhost:3000/learning` ����� ����������� � onboarding.

������� ����������� � PostgreSQL. API �� ��������� ���������������� ���: ��� ���������� ���������� ����������� runner ������������ ������ `unavailable`, � ��� ������ �����������. ��� ��������� �������� ����� ��������� execution worker/sandbox � non-root, read-only base, ��������� FS, network off, CPU/memory/PID/time/disk limits, ��� mounts/secrets/Docker socket; ������ `RUNNER_ENABLED=true` ������������.

�������� ��������: `cd apps/api && pytest -q`, `cd apps/web && npm run build`, `cd apps/api && alembic check`.


## Python Runner status

The API currently persists coding attempts but **does not execute learner code**. It remains fail-closed and returns `unavailable`. No worker or sandbox is enabled in this repository. Never set an enable flag to bypass this state.

### Required deployment before enabling execution

The planned boundary is API → authenticated private worker endpoint → one ephemeral sandbox per run. Only the worker may access the container runtime; API and web must never mount a runtime socket. The worker must be deployed on a dedicated Linux execution VM/host with no production secrets, database volume, project checkout, home-directory mounts, or general outbound access. Worker ingress must be private/firewalled (prefer mTLS; rotate worker credentials); do not publish its endpoint to the public internet. Docker daemon access is effectively host-admin access, so compromise of the worker/runtime host remains a critical residual risk; consider a stronger sandbox runtime (gVisor/Firecracker) before public beta.

Before activation, security review and integration tests must confirm: pinned image digest; fixed exercise/test/command allowlists (client cannot supply any); non-root user; network disabled; read-only root; bounded temporary filesystem; CPU, memory, PID, wall-clock and streaming stdout/stderr limits; request size/deadline/concurrency limits; strict worker-result schema; cleanup/reaper after timeout, cancellation and worker crash; and no source code or secrets in logs. AST filtering is not a security boundary for Python. Never treat `exec` restrictions or Docker alone as proof of isolation.

Configuration names reserved for a future reviewed worker are listed commented out in `.env.example`; setting them has no effect because this build has no worker client.

### Ubuntu VM manual checks (not run from this development environment)

After separately deploying the reviewed worker on its isolated execution host, check project services using `sudo docker compose ps`, then run `sudo docker compose exec api alembic upgrade head` and `cd apps/api && pytest -q`. Verify the API cannot access any runtime socket and that only the worker can reach it. From the execution host, run the worker's dedicated integration suite against disposable payloads for a passing answer, wrong answer, infinite loop, memory/PID/output exhaustion, attempted network access, and cleanup after forced worker termination. Confirm no sandbox containers remain and inspect effective cgroup/runtime limits. Do not run adversarial snippets against a production host. These checks are deployment gates; they have not been performed here.


## Adaptive diagnostic (MVP slice)

После onboarding пользователь может открыть `/assessment` с dashboard. Диагностика задаёт до четырёх authored-вопросов из конечного серверного набора; следующая сложность выбирается по правильности предыдущего ответа. Клиент получает только формулировку и варианты, не ключ ответа. Ответы и запуск оценки сохраняются в `assessment_runs` и `assessment_responses`, привязаны к пользователю текущей серверной сессии; POST защищён CSRF. Каждый вопрос до выдачи привязывается к snapshot точной `ExerciseVersion`; ответ оценивается по нему. Это начальный диагностический prior, не точная оценка профессионального уровня. Skill Graph и SkillEvidence в коде уже есть: evidence этой диагностики получает серверно выведенные `assisted`/`hint_count` из `HintReveal` той же версии до времени ответа, а не всегда independent. Она не запускает код и никак не меняет статус coding attempts: Python Runner остаётся fail-closed/`unavailable`.



## Персональный учебный план

После завершённой диагностики API автоматически сохраняет профиль проверенных навыков и персональный порядок существующих уроков. План доступен через авторизованный `GET /learning/plan`. Dashboard показывает фокус и ведёт к рекомендованному уроку. Повторная диагностика создаёт новую версию плана, а `LessonCompletion` сохраняет уже пройденные уроки.

В Linux после обновления кода примените миграции: `sudo docker compose exec api alembic upgrade head`. Затем проверьте сценарий регистрация → onboarding → `/assessment` → dashboard → рекомендованный урок.
