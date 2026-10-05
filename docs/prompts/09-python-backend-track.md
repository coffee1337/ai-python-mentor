# Промт 09 — Трек Python Backend

## Роль

Ты — оркестратор проекта AI-наставник Python Backend. Твоя работа — **декомпозиция и запуск агентов**, а не написание кода.

Прочитай `.agents/skills/task-router/SKILL.md`, `.agents/skills/content-authoring/SKILL.md`, `.agents/skills/learning-domain/SKILL.md` и `.agents/skills/api-contract-design/SKILL.md`.

**Действуй сразу.** Не задавай уточняющих вопросов, не жди подтверждения и не предлагай план без действий. Первый шаг — прочитать нужные файлы, второй — запустить агентов через `spawn_agent`. Ответ без запущенных агентов считается невыполненным.

Ограничение окружения: `max_concurrent_threads_per_session = 2`. Запускай агентов волнами по 2, дожидайся результата, потом следующая волна.

## Контекст

Все промты 00–08 выполнены. Курс покрывает `python.core`, диагностика привязана к core-навыкам.

**Это главный незакрытый пробел всего MVP.** Заявленный скоуп проекта — «Python → Python Backend». В графе **48 навыков категории `python.backend`**, и у них **ноль уроков, ноль checks, ноль практики**.

Состояние по каждому навыку backend сейчас одинаковое: он существует в `SKILLS`, у него есть prerequisite edge в графе, но нет authored-контента. `LESSON_SKILLS` строится как `[(lesson["id"], lesson["skill_id"]) for lesson in LESSONS]`, то есть новый урок автоматически свяжется со своим навыком, если skill ID совпадёт.

Названия навыков в графе (сокращённо): http basics, rest api, routing, request handling, json, serialization, validation, error handling, middleware, dependencies, auth, jwt, password hashing, rate limiting, openapi, websockets, sql basics, postgresql, sql select, sql joins, sql indexes, transactions, isolation, migrations, sqlalchemy core, sqlalchemy orm, relationships, n plus one, connection pooling, caching, redis basics, docker basics, linux cli, git basics, git branching, ci basics, ci testing, structured logging, observability, security basics.

Принятые решения — в `docs/decisions.md`.

## Задача

### 1. Спроектируй трек

Дай `architect` задачу спроектировать backend-трек как **три фазы** с явными воротами:

- **Фаза 1 — HTTP и API:** http basics, rest api, routing, request handling, json, validation, error handling.
- **Фаза 2 — Данные:** sql basics, postgresql, sql select, sql joins, sql indexes, transactions, isolation, migrations, orm, relationships, n plus one, connection pooling, caching, redis.
- **Фаза 3 — Эксплуатация:** middleware, dependencies, auth, jwt, password hashing, rate limiting, openapi, websockets, docker basics, linux cli, git basics, git branching, ci basics, ci testing, structured logging, observability, security basics.

Попроси architect письменно ответить:

- в каком порядке вводить материал, чтобы prerequisite не пропускались, и почему именно так;
- где проходит граница между «узнать про SQL» и «уметь написать запрос» — практика без Runner ограничивает возможности, и это надо спроектировать заранее;
- какие навыки можно честно закрыть authored-контентом без исполнения кода, а какие требуют Runner, и что делать с последними;
- как выглядит переход между фазами и что видит ученик;
- какие навыки backend сознательно не трогаем в первой итерации, и почему.

### 2. Наполни контент

Дай `content-author` задачу писать уроки по 3–4, начиная с фазы 1. Каждая серия — отдельный вызов агента.

Требования к уроку те же, что в промте 08: skill ID, prerequisite, цель, теория, пример с проверяемым выводом, checkpoint, misconception check, практика, вывод, вопросы с объяснением каждого варианта, `ExerciseVersion`, hint ladder 1–5.

**Отдельная сложность backend-уроков:** почти все они про чужой код, а не про код ученика. Не придумывай «упражнения, где надо написать FastAPI-приложение» — его нечем проверить без Runner. Практика здесь — чтение и объяснение реального фрагмента, предсказание поведения, поиск ошибки в чужом коде.

### 3. Проверь связность и границы трека

Дай `spec-tracer` задачу проверить после каждой серии: lesson → skill → prerequisite разрешаются, ни один урок не ссылается на навык вне графа, циклов нет, каждый урок имеет check.

Дай `tester` задачу тесты на поведение: каждый опубликованный backend-урок доступен после завершения core-фазы; урок не показывается раньше своего prerequisite; граница phase 1/2/3 соблюдается.

### 4. Покажи прогресс

Дай `ui-designer` задачу: как показать три фазы и прогресс внутри фазы на dashboard и в плане — без графиков без данных и без процентов как факта. Разрешай вёрстку `frontend-implementer`.

## Ограничения

- Runner fail-closed: код ученика не исполняется. Не обещай ученику выполнение заданий и не пиши это в тексте урока.
- Не расширяй scope: backend-трек и только. Ни C++, ни ML, ни Kubernetes, ни микросервисов.
- Не переименовывай существующие 32 урока.
- Не выдавай проценты mastery как факт уровня.
- Не добавляй в текст уроков готовые решения там, где цель — самостоятельная практика.

## Критерий готовности

Фаза 1 трека `python.backend` полностью покрыта уроками, у каждого skill ID, prerequisite и check; связи с графом разрешаются; переход между фазами виден в плане; `pytest`, `npm run lint`, `npm run build` зелёные.

В отчёте укажи: дизайн трёх фаз, список новых уроков со skill ID, точный вывод проверок, какие навыки отложены и на каком основании, что осталось непроверенным.
