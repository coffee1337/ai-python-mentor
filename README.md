# Набор агентов для AI-наставника

Скопируйте содержимое в корень репозитория. В наборе 7 Codex-агентов (`.codex/agents/`), 6 скиллов (`.agents/skills/`), проектный `AGENTS.md` и схема выбора моделей.

| Агент | Модель по умолчанию | Эскалация |
|---|---|---|
| orchestrator | Space Bunny / DeepSeek V4.1 Flash | GPT 6.1 Sol для сложной декомпозиции |
| implementer | DeepSeek V4.1 Flash; Space Bunny для микро-задач | GPT 6.1 Sol при сложной логике |
| architect | GPT 6.1 Sol | GPT 6 Astra / Claude Opus 5 для критичного решения |
| reviewer | GPT 6 Luna / Claude Sonnet 5 | GPT 6.1 Sol или Opus при риске |
| tester | DeepSeek V4.1 Flash | GPT 6 Sol для сложной диагностики |
| learning-content | Claude Sonnet 5 / GPT 6 Luna | Opus 5 для экспертной проверки |
| security-reviewer | только по запросу, GPT 6.1 Sol / Opus 5 | — |

Список пользователя содержит display names, но не API ID. Поэтому конфиги не фиксируют вымышленные slug-и: точный `model` нужно вставить из `cheapvibecode-models.json` после установки. Пока `model` пропущен, агент наследует модель сессии. Коэффициенты расходов относительные; сверяйте usage провайдера.

Оркестратор выбирает только нужные роли: маленькая правка — implementer; фича — implementer и целевой tester; доменная модель/миграция — architect, затем implementer/tester/reviewer; sandbox/auth/PII — security-reviewer. Дорогую модель включать по сигналам неоднозначности, двум неудачным попыткам или высокому риску. Не передавать весь проект и полную историю без необходимости.

Эти конфиги задают роли, но не включают автоматическую диспетчеризацию; основной Codex-агент должен делегировать им задачи. Установщик провайдера из второго файла скачивает каталог моделей; не редактируйте глобальный config/ключи ради этого набора.

---

# AI-наставник Python Backend

Next.js/React web, FastAPI API, PostgreSQL, SQLAlchemy и Alembic в структуре modular monolith. Доступны регистрация/вход, onboarding, профиль и авторский учебный маршрут.

## Требования

- Docker Compose (рекомендуемый способ локального старта), либо Node.js 22+, Python 3.12+ и PostgreSQL 16+.

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

API: `GET /learning/path`, `GET /learning/next` (возвращает `null` после завершения), `GET /learning/lessons/{id}`, `POST /learning/lessons/{id}/complete` с `{"answer":"6"}` и существующим CSRF-токеном. Все endpoints требуют сессию и завершённый onboarding. Клиент не передаёт user ID, статус завершения или оценку. Ответ-ключ не включается в lesson response; запись завершения уникальна по пользователю и версии урока.

Это фиксированный стартовый маршрут, не адаптивная диагностика. Сохраняется evidence успешного авторского quiz; помощь наставника сохраняется отдельно и не доказывает самостоятельность. В уроке есть контекстный AI-чат с подсказками и наводящими вопросами, без исполнения пользовательского кода. Для включения задайте на сервере `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL` и `AI_GATEWAY_API_KEY`; endpoint должен принимать HTTPS POST с `{model,messages,max_completion_tokens}` и возвращать ровно один `choices[0].message.content` (Chat Completions-compatible). Пустая конфигурация отключает чат; ключ не попадает в web и не логируется. Изменение смысла урока/ответа требует нового versioned ID.

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

API: из `apps/api` установите зависимости и выполните `pytest`. Web: из `apps/web` — `npm install`, затем `npm run build` или `npm run lint`.

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
не HTML. Получение помощи перед quiz сохраняет `authored_quiz_assisted` вместо
`authored_quiz_correct`; никакие mastery-оценки не повышаются.
Запрет полного решения в промпте не является гарантией поведения модели.
UI показывает последние 50 сообщений, ошибки и явный retry; старшие страницы
доступны через API. Нет token/cost billing, автоматического удаления истории или
адаптивной диагностики в этом этапе.

При конкурентных запросах PostgreSQL блокирует строку пользователя на время
ограниченного provider-вызова. SQLite-тесты не проверяют PostgreSQL row locking.
При аварийном завершении процесса между ответом провайдера и commit повтор может
снова вызвать модель: exactly-once доставка внешнего HTTP не гарантируется.
