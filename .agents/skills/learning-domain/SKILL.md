---
name: learning-domain
description: Работает с Skill Graph, mastery, evidence, curriculum и упражнениями.
---

# learning-domain

Skill — конкретное умение с prerequisites. Не своди mastery к одному числу: различай знания, практику, самостоятельность, retention, confidence. Изменения UserSkill объяснимы через evidence. Hints учитывай отдельно; полный solution не доказывает самостоятельность. Curriculum учитывает цель, gap, готовность prerequisites, забывание и время. Диагностика адаптивна. Не выдавай проценты как абсолютную истину.

Лестница подсказок — часть версионируемого exercise content: уровни раскрываются
строго по одному, `HintReveal` append-only и уникален для пользователя, версии и
уровня. Уровни 1–4 не содержат solution leakage; уровень 5 — явное решение.
Повторное раскрытие не увеличивает число использованных уровней и не меняет
старую версию контента.

Evidence для authored assessment/knowledge-check exercise получает assistance
только сервером: считаются distinct `HintReveal.level` текущего session user и
точной `ExerciseVersion`, причём только если `HintReveal.revealed_at` не позже
времени конкретного response/attempt. `hint_count` и `assisted` должны совпадать с этим
вычислением; подсказки уменьшают independent credit детерминированно, а
уровень 5 не доказывает самостоятельность.

Источники до snapshot migration с `exercise_version_id = NULL` не fallback-ятся
на authored current version: после backfill v1 остающиеся NULL отвергаются
`InvalidEvidence`, а не получают независимый credit.

Стабильные public IDs authored `LESSONS`/`CHECKS` с суффиксом `-v1` immutable:
изменение публичного текста требует нового ID/версии, а не редактирования
исторической записи. `ExerciseVersion` + `ExerciseHint` — граница
версионирования hint-content; `ExerciseVersion.content_snapshot` хранит
неизменяемый authored lesson/check/assessment/hint content, который был
опубликован для этой версии. Если authored dict изменился, старую версию
нельзя переписывать или дозаполнять текущим контентом: публикуется новая
версия; неизвестные legacy rows с `NULL` snapshot не fallback-ятся на current
authored content. Каждый authored assessment question, в том числе без hint
ladder, фиксирует `AssessmentRun.current_exercise_version_id` до выдачи
prompt/choices и проверяет answer по этому snapshot; legacy in-progress NULL
отвергается 409. Published version нельзя удалить, пока на неё ссылаются
hints, reveals или source snapshots: FK `RESTRICT`, никаких cascade/SET NULL
для этой границы. Полноценный content CMS не входит в MVP.

Prerequisite readiness едина для learning path, `accessible_lesson`, curriculum
и learning plan. Completion подтверждает только primary `skill_id` из точного
immutable lesson snapshot; старые completion rows без версии используют
явный legacy-ID registry. Secondary `LessonSkill` links — coverage metadata, не
completion evidence. Каждый навык в prerequisite closure должен иметь primary
completion либо достигнуть существующего curriculum mastery fallback `>= 0.75`;
не рекомендовать и не выдавать закрытый урок, кроме продолжения уже pending
flow на его exact bound version.

Knowledge-check GET creates or reuses one opaque pending server session per
user and lesson, binding the flow to the exact `ExerciseVersion`; POST grades
that pending snapshot and consumes the session, never re-resolving the current
authored version. A missing version or snapshot is a controlled 409.
Knowledge-check POST without a pending GET session is 409; a failed validation
does not consume it. Lesson GET/next likewise creates or reuses one pending
`LessonSession` per user/lesson; completion grades its exact snapshot and
records `LessonCompletion.exercise_version_id`, consuming the binding on a
correct attempt. Direct lesson POST may bind only before any GET flow for
that user/lesson; missing or invalid prior binding is 409. Hints follow the
pending lesson/check version, not mutable authored current content; conflicting
pending versions are 409 rather than silently attributing help to the wrong
version. Historical completions without trustworthy version retain NULL.
Answer keys и другие grading secrets не входят в API responses.
`SkillEvidence` enforces `hint_count BETWEEN 0 AND 5` and the assistance
pairing: independent evidence has `assisted = false` with `hint_count = 0`;
assisted evidence has `assisted = true` with at least one hint.

Coding practice has a separate persistence boundary: every new
`CodingAttempt` is bound to the exact immutable `ExerciseVersion`, and every
validated normalized Runner result is stored in `SubmissionResult` with the
same version FK, the attempt FK, and a unique idempotency key derived from the
attempt. Legacy rows without a trusted version remain nullable and
fail-closed. A coding result may become `SkillEvidence` only through
`record_evidence(source_type="coding_attempt")` after the server proves the
attempt owner, exact attempt/result/version identity, immutable snapshot
skill mapping, current protocol, terminal `passed`/`failed` status, and
bounded `0 <= tests_passed <= tests_total` counts. `result_score` is derived
only as `tests_passed / tests_total`; the client and worker do not provide it
or the skill. `assisted`/`hint_count` are always derived server-side from
distinct `HintReveal.level` rows for the same user and exact version with
`revealed_at <= SubmissionResult.created_at`. Unavailable, timeout,
resource-violation, malformed/protocol-failure, owner-mismatch, legacy-null
version, and invalid-snapshot results receive no coding evidence. The result
and evidence link are committed atomically; if exact mapping or evidence
validation fails, the normalized result may remain for audit but no partial
mastery evidence is written.

Mistake Memory is separate from mastery: a `Misconception` is immutable
versioned authored content, while `UserMistake` is an aggregate unique by
`(user_id, misconception_code)`. The append-only `MistakeOccurrence` source
fact is unique by persisted source response and misconception, so retrying the
same response does not increment the aggregate. Recording a mistake never
writes `SkillEvidence`, `UserSkill`, or mastery directly. Current sources are
knowledge-check, assessment responses, and the version-bound terminal
coding-result path above; the fail-closed/unavailable Runner never populates
`coding_attempt`.
Classification requires an exact authored mapping for source type, exercise ID
and version, question ID, and selected wrong choice, verified against the
response's immutable content snapshot. An unmapped wrong choice is retained by
its grading flow but is not assigned a generic misconception or counted as a
personal mistake; a distractor is only a possible signal, never a diagnosis.
The initial authored mapping seed covers the six verified knowledge-check
distractors only; do not infer assessment mappings from similar wording or
choices. Assessment responses become classifiable only after their own exact
source/question/choice mappings have been reviewed and seeded.
Distinct wrong responses with the same misconception code remain one learner
history and increment its count regardless of elapsed time or correct answers
between them; reprocessing the same persisted response is idempotent.

Delayed review is a separate retention signal, not a knowledge-check or
acquisition result. It is recorded only by the review domain service against a
server-owned `ReviewSession`, the owner's due `UserSkill`, and that session's
exact immutable `ExerciseVersion` snapshot. The service derives distinct hint
levels for that owner and version up to the server-recorded completion time;
clients cannot submit `assisted`, `hint_count`, an owner ID, or a schedule.
Review creates append-only `SkillEvidence(source_type="review_attempt",
retention_only=true)` and a linked `ReviewAttempt`. It may update only the
retention projection, last-observed activity time, and due schedule; it must
not change `knowledge_score`, `independent_score`, `practice_score`,
`mastery_weight`, or `confidence`, nor award acquisition credit. The existing
mastery formula remains unchanged. `UserSkill.evidence_count` deliberately
does not count retention-only rows because the existing knowledge-check
interval policy uses that counter; review history is queried from its own
evidence/attempt records. Review mastery audits therefore keep before/after
mastery and evidence count equal.

Review intervals are an explainable, uncalibrated policy: an incorrect/partial
result schedules one day later; a fully correct result with hints schedules
three days later; independent fully correct delayed reviews progress through
7, 14, 30, then 60 days, based only on the preceding consecutive, independently
successful, schedule-applied review history. Empty review history starts at
seven days, not earlier. These are scheduling heuristics, not probabilities or
claims of measured retention; do not present them as percentages or as SM-2 /
FSRS predictions. Schedule from the actual UTC completion timestamp, including
when a review is overdue. At most one attempt per user, skill, and UTC day may
change the schedule; later same-day observations may be retained without
another schedule shift. No response or an overdue date alone is not negative
evidence and must never penalize mastery or move the schedule.

Review API sessions use a random opaque bearer token whose hash is persisted;
the API exposes only public question text/choices and never answer keys,
exercise-version IDs, database session IDs, or client-supplied grade/interval/
assistance/hint/version fields. Submitted answers are retained server-side for
idempotent replay. Curriculum review candidates have a bounded priority and
are appended only after prerequisite-ready acquisition candidates, so overdue
retention work cannot displace a higher-priority prerequisite.

Диагностика — банк вопросов, а не один экзамен. Банк покрывает все 42 навыка
`python.core` двумя вопросами на навык: `anchor` около difficulty навыка и `probe`
чуть выше. Вопрос без навыка в графе не попадает в банк: на импорте
`assessment_content` выполняется fail-closed валидация — уникальный `-v1` id,
skill существует в `SKILLS` и `category == "python.core"`, `answer` в `choices`,
difficulty в `[0.1, 0.9]` и внутри диапазона своего навыка, каждый навык покрыт.
Вопросы, опубликованные до этого правила, не переименовываются и не
переписываются — они перечислены в `LEGACY_DIFFICULTY_EXEMPT` и исключены только
из проверки диапазона difficulty.

Адаптивная ветка идёт по слотам графа, а не по всей шкале: один правильный ответ
поднимает слот на `SLOT_STEP`, неправильный опускает, слот ограничен
`[MIN_DIFFICULTY, MAX_DIFFICULTY]`. В пределах прогона навык не повторяется
подряд, вопрос не задаётся дважды, а при исчерпании банка прогон завершается
нормально, а не ошибкой. `MAX_QUESTIONS` ограничивает один прогон: банк больше
прогона, и это осознанно — диагностика даёт prior, а не точную оценку уровня.
Проценты mastery не выдаются как факт уровня.

Каждый заданный вопрос пишет ровно одну строку evidence на свой навык, поэтому
`generate_plan` обязан брать assessment-оценку для любого навыка графа, а не
через захардкоженное отображение. Иначе новые навыки банка молча выпадают из
prior, и план начинает рекомендовать то, что диагностика уже проверила.

## Принятые решения промта 09 — трек `python.backend`

Внутренняя prerequisite-цепочка backend-навыков одна и длинная, поэтому фаза
трека — это непрерывный подмножество этой цепочки, а не тематическая группа.
`BACKEND_PHASES` в `app/backend_content.py` разбивает все 48 навыков
`python.backend` на три фазы без пересечений; каждая фаза ссылается на
`skill_ids`, а урок принадлежит фазе по своему `skill_id`. Неопубликованная
фаза не показывается ученику вовсе, иначе ворота выглядели бы пустыми.

У каждого нового урока `prerequisites` обязан точно совпадать с множеством
prerequisite-рёбер его навыка в графе; `validate_graph` проверяет это при
импорте и падает при расхождении. Единственное исключение —
`LEGACY_PREREQUISITE_EXEMPT`: `conditions-v1` опубликован до этого правила, и
его контент неизменяем по решению проекта, поэтому расхождение зафиксировано
явным списком, а не переписанием урока на месте.

Первый backend-навык `backend.http_basics` требует `python.functions`, чьё
транзитивное замыкание — вся core-цепочка. Без этого ребра фаза 1 открывалась
бы новичку без core-базы и вытесняла retention-работу из учебного плана. Граф
пополняется аддитивно: новое ребро добавляется, существующие данные не
переписываются, а `seed_skill_graph` досоздаёт недостающие строки.

Прогресс фазы API отдаётся как `LearningPath.phases`: счётчик закрытых уроков,
статус и `next_lesson_id`. Проценты mastery не выдаются как факт уровня, фаза
считается завершённой только когда закрыты все её опубликованные уроки, а
статус `available` фазы требует достижимости хотя бы одного её урока.

Backend-уроки почти всегда про чужой код. Runner fail-closed, поэтому практика
в них — чтение фрагмента, предсказание вывода и поиск ошибки, а задания вида
«напишите FastAPI-приложение» запрещены. Текстовый вывод примера сверяется с
реальным запуском: `example_output` обязан совпадать с выводом `example`.

## Read-only прогресс и восстановление работы

`/learning/progress` и `/learning/today` — owned read projections существующих источников: не создавай evidence, completion, контентные версии, grading sessions или CurriculumSession при просмотре. Используй общую PrerequisiteState policy и immutable snapshot identity; acquisition и retention разделяй. Активность без evidence не выдавай за освоение; неизвестную оценку возвращай null. Календарные агрегаты с фиксированным offset должны работать на SQLite и настоящем PostgreSQL независимо от timezone соединения.

Source GET попыток/проектов требует owner до поиска связанных версий. Не возвращай hidden tests/answer keys/hash/idempotency или source в публичном portfolio. Preview/restore не submit/run/grade. Код восстанавливается лишь при exact exercise/public version/language/mode; legacy unknown bindings доступны только для просмотра. Не теряй исходный черновик при замене, смене шага урока или недоступном browser storage. Локальные drafts user/version scoped и удаляются при logout/account deletion; step/answer draft не является серверным результатом проверки. Latest milestone submission не выводи из глобально обрезанной истории проекта.
