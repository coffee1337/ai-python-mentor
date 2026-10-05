# Незавершённые этапы AI Programming Tutor

> **УСТАРЕЛО. Не используй как источник правды.**
>
> Этот файл отражает состояние на 3 октября 2026 года и расходится с кодом: он
> утверждает, что Review Scheduler, Mistake Memory и Submission results не реализованы,
> а курс ограничен двумя уроками. Всё это неверно — см. фактическое состояние ниже.
>
> Актуальная карта пробелов: `docs/prompts/README.md`.
>
> Дата пересмотра: 5 октября 2026 года. Проверено чтением кода.

Сопоставление выполнено по спецификации и текущему коду. Наличие названия функции в README или модели само по себе не считается завершённой реализацией.

## Уже работает (базовая версия)

- Регистрация, сессии, CSRF, onboarding и цель пользователя.
- Короткая authored adaptive assessment; ответы хранятся по владельцу.
- Персональный порядок двух текущих уроков и progress completion.
- AI-наставник через AI Gateway.
- Редактор и сохранение попыток, но код не исполняется.
- Authored knowledge checks с серверной оценкой, объяснениями и сохранением повторных попыток.
- Базовая UserSkill mastery-запись и next_review_at после knowledge check.

## Есть в коде и SQLite/API-тестах; production runtime не подтверждён

Реальный PostgreSQL, row locking, изоляция Runner и browser E2E здесь не проверялись.

- Skill Graph 0010: 90 навыков, prerequisite edges, идемпотентный seed, API и связи двух уроков.
- SkillEvidence/SkillMasteryAudit 0011, `record_evidence` и server-derived attribution подсказок для assessment/knowledge check.
- Детерминированный curriculum engine 0012 и AI curriculum 0013; vacancy/practice/review остаются unavailable.
- `AIUsageLedger` 0013/0014 пишется из AI curriculum и mentor chat; это не token/cost billing.

## Незавершённые/частично реализованные этапы

### 1. Skill Graph — базовый граф есть, полный учебный контур нет

Статус: SQLite/API-тесты есть, PostgreSQL runtime unverified. Миграция `0010_skill_graph`, модели `Skill`/`SkillEdge`/`LessonSkill` (таблицы `skills`/`skill_edges`/`lesson_skills`), идемпотентный `seed_skill_graph`, router `/skills` и тесты graph/seed/prerequisites есть. Seed содержит 90 навыков (`python.core` и `python.backend`) и 93 prerequisite edges; `validate_graph` требует 80–150 навыков и ацикличность. К урокам привязаны только `variables-v1` и `conditions-v1` (таблица `lesson_skills`), и learning path использует эти prerequisites. Полнота курса незавершена. Не хватает:

- контента и evidence для остальных навыков графа;
- проверки миграции и seed на реальном PostgreSQL (здесь не проверялась, runtime unverified);
- полного курса, который покрывает граф, а не два урока.

### 2. Mastery/evidence — журнал и attribution подсказок подключены, контур ещё неполный

Миграция `0011_skill_evidence` добавляет append-only `SkillEvidence` и `SkillMasteryAudit`; `record_evidence` обновляет проекцию `UserSkill` и принимает `assisted`/`hint_count`. Assessment и knowledge check получают эти значения через `derive_assistance`: сервер считает distinct раскрытые `HintReveal.level` текущего пользователя для точной `ExerciseVersion`, если раскрытие было до конкретного response/attempt. `hint_count` — фактическое число уровней 1–5, а assisted evidence снижает independent credit; answer keys не входят в API responses. Не хватает:

- единого учёта quiz, assessment, coding submission и spaced review: coding
  evidence начисляется только для сохранённого protocol-validated terminal
  result с exact snapshot и server-derived hint attribution;
- полноценной retention/forgetting модели — `retention_score` равен последнему `result_score`, `confidence` упрощён до веса evidence;
- проверки row locking на реальном PostgreSQL (здесь не проверялась).

### 3. Curriculum Engine и персональный план — частичный deterministic engine

Curriculum уже есть в коде и SQLite/API-тестах: миграция `0012_curriculum_engine`, `build_curriculum` и `GET/POST /learning/curriculum`; ревизия учитывает skill gap, importance, goal fit, prerequisite readiness и окно 20–60 минут (`MIN_SESSION`/`MAX_SESSION`) — prereq/goal/mastery и сессии 20–60 в коде присутствуют. Authored-уроки по-прежнему занимают по 10 минут, поэтому сессия часто короче цели. Не реализованы:

- vacancy requirements: `vacancy_fit` явно `unavailable`, отдельных требований вакансии нет (нет forgetting-risk/vacancy requirements);
- practice и review activities: coverage помечает оба как `unavailable` (`vacancy`/`practice`/`review unavailable`), активности остаются уроками;
- forgetting risk как фактор порядка: есть только `review_due`/`stale_evidence` по `next_review_at` и 30 дням, без модели забывания (нет forgetting-risk как фактора порядка);
- чередование нового материала, практики и review.

### 4. Review Scheduler — поле есть, scheduler нет

Есть только поле `UserSkill.next_review_at`; полноценного review scheduler/API/UI/evidence нет.

`UserSkill.next_review_at` выставляется после knowledge check простым интервалом (1 день при неуспехе, до 14 при успехе). Curriculum может добавить причину `review_due`, но это не очередь повторения. Отсутствуют:

- отдельная очередь/модель `review_schedule`;
- экран и API повторения на сегодня;
- результат delayed review как retention evidence;
- возврат просроченных навыков отдельным review и правила переноса review.

### 5. Mistake Memory

Не реализованы:

- сущности mistakes/user_mistakes;
- каталог misconceptions и связь с навыками;
- выявление повторяющихся ошибок;
- подбор remediation lesson/exercise по ошибке;
- структурированная память ошибок для AI-наставника.

### 6. Hint ladder — базовая ladder реализована, follow-up ещё нет

Выполнена базовая ladder уровней 1–5 (`direction`, `concept`, `step`, `pseudocode`, `solution`) через `POST /learning/exercises/{exercise_id}/hints`. Запрос требует CSRF и `Idempotency-Key`; сервер раскрывает только следующий уровень, сохраняет `HintReveal` append-only, делает повтор идемпотентным и связывает hint с точной `ExerciseVersion` текущего lesson/check flow. `derive_assistance` использует только раскрытия того же пользователя/версии до времени ответа; `hint_count` — число distinct раскрытых уровней, а уровень 5 не доказывает самостоятельность. Не реализован follow-up exercise без подсказки. Отдельный маркер `LessonCompletion.evidence_type=authored_quiz_assisted` на `/complete` остаётся helper field, не является `SkillEvidence` и не калибрует mastery.

### 7. Учебный контент и Lesson Engine

Есть две versioned lessons (`variables-v1`, `conditions-v1`), prerequisites/lesson links (`lesson_skills` и learning path) и authored knowledge-check primitives для них, но нет полного курса/units/checkpoints/misconceptions. Спецификация требует существенно большего Python Backend курса; мини-практика не проверяется изолированным Runner. Prerequisites покрывают только Skill Graph и learning path двух уроков, но не курс целиком.

## Заблокировано до отдельного безопасного Linux Runner

### 8. Изолированный Python Runner и объективная проверка кода

API сохраняет coding attempts, но Runner намеренно fail-closed и возвращает unavailable. Пользовательский код нигде не запускается; unavailable не является успехом. Не реализованы:

- отдельный Linux execution worker и очередь;
- public/hidden tests и нормализованные результаты;
- проверенные timeout, CPU/memory/PID/disk/output лимиты;
- network isolation, non-root, read-only base и временная FS;
- cleanup/reaper после timeout, отмены или сбоя;
- безопасная API-worker интеграция и security-reviewed deployment;
- adversarial/integration тесты изоляции.

### 9. Полноценный submission pipeline

Не хватает асинхронных job statuses и runner findings. Нормализованный
`submission_results` и узкий evidence-мост для trustworthy terminal result
уже есть; unavailable/timeout/resource/protocol failure остаются
fail-closed без mastery evidence.

### 10. Monaco

Сейчас editor — textarea. Не реализованы Monaco, подсветка синтаксиса и IDE-подобная диагностика.

## Отсутствующие крупные MVP/roadmap этапы

### 11. Vacancy Analyzer

Нет загрузки вакансии/URL, извлечения требований, уровня важности, mapping требований на Skill Graph, gap analysis и roadmap под вакансию.

### 12. Projects и portfolio evidence

Нет проектов, milestones, project submissions, portfolio evidence и проектной оценки навыков.

### 13. Repository intelligence

Нет repository import/status, индексирования файлов и символов, code relations/findings, async ingestion и большого code review.

### 14. RAG/knowledge base

AI Gateway есть, но нет retrieval pipeline, векторного хранилища/pgvector, embeddings и versioned knowledge corpus.

### 15. Async jobs/Redis

Нет Redis/очереди/worker orchestration для sandbox, review, repository ingestion и notifications.

### 16. Billing и AI usage accounting

`AIUsageLedger` пишется для `ai_curriculum` (миграции `0013_ai_curriculum` и `0014_ai_usage_ledger_user_index`) и mentor chat. Mentor записывает операцию `mentor_chat` для завершённых ответов, gateway errors и cache hits; character counts пишутся всегда, provider token fields — только при валидных integer values. Это ограниченный usage ledger, не полноценный billing: нет подписок, тарифов/credits, sandbox accounting, per-user/global budgets и anomaly alerts; token/cost billing нет.

### 17. Telegram и уведомления

Нет Telegram bot, reminders, quick tutor, расписания и notification preferences.

### 18. Admin и production operations

Нет admin UI/basics, управления контентом, monitoring dashboards, alerts, backup/restore drills и operational runbooks.

### 19. Account lifecycle/privacy

Не реализованы или не подтверждены account deletion, data export, retention policy для исходного кода/AI-истории и privacy policy.

## Проверки, требующие Linux/развернутого окружения

В текущей Windows-среде не подтверждены реальные PostgreSQL/Compose upgrade и end-to-end browser → API → PostgreSQL. Runner deployment/изоляция также не подтверждены. После обновления проекта в Linux:

```bash
sudo docker compose exec api alembic upgrade head
sudo docker compose up --build
cd apps/api && pytest -q
cd apps/web && npm ci && npm run lint && npm run build
```

Проверки Runner выполнять только на отдельной disposable Linux execution VM, не на production-хосте.

## Рекомендуемый порядок следующих этапов

1. Добавить follow-up exercise без подсказки после solution и отдельно решить attribution помощи из mentor-чата; текущий `HintReveal` не учитывает свободный chat.
2. Завершить Review Scheduler с delayed review и retention evidence.
3. Закрыть vacancy/practice/review gaps в curriculum, не расширяя граф ради количества навыков.
4. Добавить Mistake Memory; базовая hint ladder уже есть, follow-up остаётся отдельной задачей.
5. Расширять курс Python Backend по мере готовности content/evidence model.
6. Подключать Runner только после отдельного security-reviewed Linux execution worker.
7. Затем vacancy analyzer; после проверки core — projects, RAG, billing, Telegram и admin.

## Вне текущего scope без отдельного запроса

C++, React IDE, ML, Kubernetes, микросервисы и полноценный анализ больших репозиториев.
