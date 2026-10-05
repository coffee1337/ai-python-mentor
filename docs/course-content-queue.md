# Очередь наполнения курса: Python core, волна 1

Статус: архитектурный proposal, 2026-10-04. Это отдельный design-артефакт; runtime, authored lessons/checks, skill graph, mappings и существующие версии этим документом не меняются.

## Объём и правило очереди

Предлагается **16 последовательных уроков** (включая действующие): первые 16 узлов Python-цепочки от `python.variables` до `python.tuples`. Так в пределах лимита охватываются основы, функции и первые структуры данных. Это не все первые 20 узлов: `python.sets`, `python.dictionaries`, `python.slicing`, `python.iteration` — следующая волна, не должны втискиваться за счёт объединения prerequisite-ступеней.

Сложность — ожидаемая для новичка по шкале 1–5 (1 — один новый термин/прямое распознавание; 2 — применение одного правила; 3 — несколько последовательных шагов). Это не mastery и не проценты. Для каждой строки указан **непосредственный prerequisite**; resolver обязан требовать и его транзитивное closure по `SkillEdge(relation="prerequisite")`. Для корневого узла prerequisite отсутствует.

| № | Public lesson ID | Primary skill ID | Непосредственный prerequisite | Сложность | Knowledge check: что должен отличать/предсказывать ученик |
|---:|---|---|---|---:|---|
| 1 | `variables-v1` (существует) | `python.variables` | — (корневой) | 1 | Вычислить значение после последовательных присваиваний; объяснить, что правая часть вычисляется до перепривязки имени. |
| 2 | `data-types-v1` (новый) | `python.data_types` | `python.variables` | 1 | Различить тип значения и имя-переменную; распознать базовые литералы и понять результат простого смешения типов без углубления в coercion. |
| 3 | `conditions-v1` (существует) | `python.conditionals` | `python.data_types` | 2 | Выбрать ветку по сравнению, включая равенство на границе; отличить независимый `if` от связки `if/else` и учесть блоки по отступам. |
| 4 | `loops-v1` (новый) | `python.loops` | `python.conditionals` | 2 | Проследить конечный `for`/`range` по числу итераций и объяснить, почему верхняя граница `range` не включается; обнаружить простой off-by-one. |
| 5 | `functions-v1` (новый) | `python.functions` | `python.loops` | 2 | Отличить определение функции от вызова; установить, какие строки выполнятся только при вызове. |
| 6 | `parameters-v1` (новый) | `python.parameters` | `python.functions` | 2 | Сопоставить позиционные и именованные аргументы параметрам; определить результат вызова при корректном соответствии. |
| 7 | `return-values-v1` (новый) | `python.return_values` | `python.parameters` | 2 | Отличить `return` от `print`; предсказать возвращаемое значение и поведение кода после раннего `return`. |
| 8 | `scope-v1` (новый) | `python.scope` | `python.return_values` | 3 | Разобрать локальное имя функции и имя снаружи; определить, почему присваивание локальному имени само по себе не перепривязывает внешнее. |
| 9 | `mutability-v1` (новый) | `python.mutability` | `python.scope` | 3 | Отличить изменение изменяемого объекта через alias от перепривязки имени; предсказать, какие ссылки увидят изменение. |
| 10 | `strings-v1` (новый) | `python.strings` | `python.mutability` | 2 | Различить строку и её представление; распознать неизменяемость строки и предсказать конкатенацию/форматирование без срезов. |
| 11 | `numbers-v1` (новый) | `python.numbers` | `python.strings` | 2 | Рассчитать результат целочисленного деления, обычного деления и остатка; не смешать `/` и `//`. |
| 12 | `booleans-v1` (новый) | `python.booleans` | `python.numbers` | 2 | Отличить `bool`-значение от числового результата сравнения; распознать `==` как сравнение значений, не идентичности объектов. |
| 13 | `truthiness-v1` (новый) | `python.truthiness` | `python.booleans` | 2 | Предсказать ветку для `0`, ненулевого числа, `""` и непустой строки; не сводить truthiness только к литералам `True/False`. |
| 14 | `comprehensions-v1` (новый) | `python.comprehensions` | `python.truthiness` | 3 | Прочитать порядок выражения и `for`/`if` в простой comprehension и предсказать отфильтрованный результат. |
| 15 | `lists-v1` (новый) | `python.lists` | `python.comprehensions` | 2 | Отличить индекс от значения, применить `append` и предсказать изменение того же списка; без срезов. |
| 16 | `tuples-v1` (новый) | `python.tuples` | `python.lists` | 2 | Различить tuple и list по синтаксису/изменяемости; проследить распаковку при совпадающем числе элементов. |

Идентификаторы существующих уроков не переименовывать: особенно `variables-v1` и `conditions-v1`. Новые stable IDs публикуются только вместе с `CHECKS` под тем же lesson ID, `ExerciseVersion`/snapshot и, для практики, пятиуровневой ladder. Семантическое изменение — новая версия/ID, исправление опечатки не требует смены версии. Код ученика не исполнять: Runner остаётся fail-closed; практика этой волны может проверять чтение/объяснение фиксированного примера и статические ответы, но не запуск отправленного кода.

## Почему именно этот порядок

Порядок — точная префиксная последовательность Python prerequisite-рёбер в `apps/api/app/skill_graph.py`, а не тематическая сортировка или случайная выдача: variables → data_types → conditionals → loops → functions → parameters → return_values → scope → mutability → strings → numbers → booleans → truthiness → comprehensions → lists → tuples. Например, задачу на цикл не ставим перед ветвлением, вызов функции — до понимания циклов, параметры — до определения/вызова, а comprehension — до truthiness. Каждая строка даёт authored content и check для skill, который открывает следующую строку.

`curriculum._prerequisite_closure` строит полный набор предков. `build_curriculum` выбирает урок лишь если все предки либо покрыты завершёнными LessonSkill-связями, либо каждый набрал mastery ≥ 0.75. Но есть важная разница: `learning_path`/`accessible_lesson` закрывают урок только по завершённым урокам, связанным через `LessonSkill`; они не используют mastery fallback. Поэтому адаптивный план может содержать рекомендацию, которая ещё отображается как `locked` на learning path/при GET. Кроме того, среди одновременно готовых кандидатов `build_curriculum` сортирует по adaptive priority, а не гарантирует номер таблицы. Таблица задаёт pedagogical order, но не обещает неизменный UI-маршрут без проверки этих стыков.

## Release gate: решения по двум blocking issue до authoring

Этот gate **обязателен до запуска content-author**. Он является архитектурным решением для следующей реализации, а не изменением текущего runtime: в этой follow-up задаче не меняются код, схема, seed, миграции, authored content и существующие public IDs. Нельзя трактовать его как разрешение редактировать `variables-v1` или `conditions-v1`.

### Gate A — mapping `variables-v1` → `python.data_types` и исторические completions

**Факты текущей реализации.** В `apps/api/app/skill_graph.py` сейчас есть два `LessonSkill` для `variables-v1`: `python.variables` и `python.data_types`. `seed_skill_graph` только добавляет отсутствующие строки и не удаляет старые. И `apps/api/app/learning.py`, и `apps/api/app/curriculum.py` строят `completed_skills` через все `LessonSkill` у завершённого урока; поэтому старое completion variables может открыть closure для `python.conditionals` до data-types. `apps/api/app/learning_plan.py` дополнительно сохраняет adaptive order и сам по себе не проверяет prerequisite readiness.

**Каноническое решение для новых данных.** Удалить ошибочную secondary-пару из authored `LESSON_SKILLS` (primary ID существующего урока не меняется) и добавить mapping нового урока при его авторинге. Итоговые связи:

- `variables-v1` → `python.variables`;
- новый `data-types-v1` → `python.data_types`;
- `conditions-v1` → `python.conditionals`.

Не выдавать completion `variables-v1` за completion `data-types-v1` и не создавать backfill completion/evidence для types. Все существующие completions и exact `exercise_version_id` snapshots остаются нетронутыми; завершённый `conditions-v1` остаётся completed, но не создаёт evidence по `python.data_types`.

**Минимальный backward-compatible runtime step.** До первой серии authoring implementer должен:

1. Ввести один общий resolver prerequisite readiness. Completion-derived skills брать из primary skill неизменяемого lesson snapshot (для исторических NULL-version rows — из стабильного legacy-ID registry), а не из всех `LessonSkill` links. Сохранить текущую curriculum-альтернативу: prerequisite считается готовым также при уже существующем mastery ≥ 0.75 по текущему `_mastery`; формулу/порог не менять. Secondary links остаются для coverage, но не открывают prerequisite сами по себе.
2. Применить один readiness resolver в `apps/api/app/learning.py` (`learning_path`/`accessible_lesson`), `apps/api/app/curriculum.py` (`build_curriculum`) и `apps/api/app/learning_plan.py` (генерация и выдача статусов). `conditions-v1` можно рекомендовать/отдать только если `python.data_types` подтверждён primary completion `data-types-v1` либо уже имеющимся mastery ≥ 0.75; никогда — одной legacy secondary link от variables. Старые curriculum revisions/plan rows не переписывать, но current API не должен выбирать locked row как next/recommended; новый revision строить по общей readiness-политике. Pending `LessonSession`/`KnowledgeCheckSession` сохраняет свой exact snapshot binding; не rebinding. По locked lesson продолжить только уже bound exact-version flow либо вернуть controlled 409 и потребовать после prerequisites открыть новую сессию.
3. Не менять `PASS_SCORE`, mastery formula, `SkillEvidence` или source attribution. Не переиздавать и не перепривязывать уже созданные `LessonSession`/`KnowledgeCheckSession`; pending flow, начатый до релиза, должен завершаться на своей сохранённой версии либо явно получить контролируемый `409`, но не молча переехать на новый snapshot.

Так как `seed_skill_graph` add-only, изменение статического seed не удалит legacy row из БД. Нужна следующая обратимая Alembic-миграция (ожидаемый файл `apps/api/migrations/versions/0028_correct_variables_data_types_mapping.py`; head сейчас `0027_review_api`): upgrade удаляет только natural key `(variables-v1, python.data_types)` из `lesson_skills`, downgrade восстанавливает ровно эту пару, если её нет. Миграция не трогает completions, attempts/evidence, `ExerciseVersion`/snapshots, sessions или планы. Незавершённый старый plan item conditions может стать locked/не-recommended, но исторические completions не отзываются и старый план не переписывается. Проверить upgrade/downgrade с sentinel completion + version/snapshot и сохранностью прочих mappings на SQLite и локальном PostgreSQL round trip.

**Минимальные поведенческие тесты до authoring:**

- после variables без data_types mastery доступен только `data-types-v1`, incomplete `conditions-v1` locked;
- legacy DB: migration удаляет только ошибочную link, и variables completion не создаёт data-types evidence;
- существующее completion conditions остаётся completed, но incomplete `conditions-v1` недоступен без data-types completion или валидного mastery fallback;
- уже созданные session/snapshot bindings не меняют version;
- `learning_path`, `accessible_lesson`, `plan_response` и `build_curriculum` одинаково учитывают primary completion и существующий mastery fallback; ни один интерфейс не рекомендует locked lesson.

Целевые файлы runtime/test: `apps/api/app/skill_graph.py`, `apps/api/app/learning.py`, `apps/api/app/curriculum.py`, `apps/api/app/learning_plan.py`, `apps/api/migrations/versions/0028_correct_variables_data_types_mapping.py`, `apps/api/tests/test_learning.py`, `apps/api/tests/test_learning_plan.py` и reversible migration regression test. DB table schema не меняется. До прохождения этих tests content-author не добавляет следующую серию.

### Gate B — immutable public v1/snapshots против расширенного lesson/check content

**Запрет.** Нельзя дополнять или «улучшать» существующие `variables-v1`/`conditions-v1` в `apps/api/app/learning_content.py`, `apps/api/app/knowledge_check_content.py` или `EXERCISE_HINT_LADDERS`, если это меняет опубликованный смысл/текст. `ExerciseVersion.content_snapshot` — immutable boundary: существующие rows, hint reveals, attempts и completions читаются только из своего snapshot. Migration `0017_exercise_content_snapshots` не является местом для дозаполнения старых v1 текущим authored dict.

**Backward-compatible content contract.** `variables-v1` и `conditions-v1` остаются неизменяемыми legacy-public versions, а не целями authoring wave: их старый lesson/check shape и общий per-question explanation допустимы только для чтения по schema 1 и их уже связанным snapshots. Не редактировать их и не создавать под теми же IDs новые snapshots, выдавая это за upgrade v1. Все новые public lesson IDs из очереди, начиная с `data-types-v1`, получают полный expanded authored shape: `goal`; `prerequisites` как skill IDs; `theory`; `example` и `expected_output`; `checkpoint`; `misconception_check`; `practice`; `conclusion`. Каждый новый knowledge check получает per-choice explanation. Если смысл существующего урока потребуется изменить, добавить новый public lesson ID/version (например, `variables-v2`) отдельным явным обновлением очереди; новый ID получает собственный exercise snapshot, completion старого ID не переносится. Не использовать новую `ExerciseVersion.version` под тем же `variables-v1` как обход: `LessonCompletion` ключуется по public lesson ID. Новая версия получает собственный `ExerciseVersion` и пятиуровневую ladder; levels 1–4 не содержат solution leakage, level 5 — явное решение. Runner остаётся fail-closed: не добавлять упражнения, требующие исполнения кода ученика.

Чтобы не ломать старые snapshot rows, implementer должен сделать **additive read path**, а не in-place rewrite:

- `apps/api/app/exercise_snapshots.py`: сохранять legacy snapshot shape как есть; для нового extended shape использовать явно распознаваемый `schema_version=2` и валидировать полный набор полей только для новых snapshots. В `apps/api/app/exercise_hints.py` при совпадении `(exercise_id, version)` сравнивать полный authored snapshot с persisted snapshot и отклонять drift как version conflict. Из-за ключа `LessonCompletion(user_id, lesson_id)` содержательное изменение урока публиковать под новым public lesson ID (`*-v2`), с новыми check IDs и новым exercise snapshot; bump только integer `ExerciseVersion.version` под старым lesson ID не переносит completion safely. `NULL` legacy snapshot не восстанавливать из mutable authored dict; оставить контролируемое unavailable поведение;
- `apps/api/app/learning.py` и его response model: принимать schema 1 legacy и schema 2 extended; новые поля отдавать additive, а отсутствие полей в старом snapshot не считать повреждением. Existing v1 response shape remains supported; смысловое изменение — новый public lesson ID (например, `variables-v2`), не запись поверх `variables-v1`; прежние completions и sessions остаются привязаны к legacy ID/version. Обновить `apps/web/app/learning/page.tsx`, чтобы новые поля отображались, сохранив legacy rendering;
- `apps/api/app/knowledge_check_content.py`: для новых checks хранить explanation для **каждого** choice в детерминированном ключе (например, `choice_explanations: {choice: explanation}`) и требовать точное покрытие всех choices; legacy одно поле `explanation` оставить только для чтения старых snapshot/checks;
- `apps/api/app/knowledge_check.py`: валидировать legacy `explanation` для schema 1 и точное `choice_explanations` coverage для schema 2; при grading брать explanation по фактически выбранному варианту из bound snapshot и сохранять его в существующее `KnowledgeCheckResponse.explanation`. GET не раскрывает answer key или все explanations; POST может вернуть rationale выбранного варианта в существующем совместимом формате;
- `apps/api/app/learning_content.py`: добавлять новые lesson IDs и перечисленные extended fields; `apps/api/app/knowledge_check_content.py`: для каждого check хранить `choice_explanations` с одним непустым объяснением на каждый допустимый choice. `apps/api/app/exercise_hints.py`: новые lesson IDs публиковать со своими ladder/exercise versions; старую version не дозаполнять и не переиспользовать для другой практики.

Это additive JSON-content/API/UI compatibility step, а не DB migration: `ExerciseVersion.content_snapshot` уже хранит JSON, новой DB-колонки не требуется; migration `0017` и её hardcoded legacy snapshots не менять. Нужны regression tests: опубликованный v1 snapshot остаётся неизменным и читаемым; content drift без bump version отвергается; новый extended snapshot фиксируется ровно для нового ID/version; per-choice explanation соответствует каждому choice, но GET не раскрывает grading data. Целевые тесты — `apps/api/tests/test_learning.py`, `apps/api/tests/test_knowledge_check.py`, `apps/api/tests/test_learning_migration.py`. Новые lesson-поля добавить в response model `apps/api/app/learning.py` и отобразить в `apps/web/app/learning/page.tsx`, сохранив legacy rendering.

### Неподлежащая изменению последовательность запуска

1. **Architect/implementer:** закрыть Gate A и Gate B, добавить поведенческие regression tests; не писать новый authored content до зелёного набора.
2. **Content-author:** добавить только новые IDs из таблицы, начиная с `data-types-v1`; prerequisites указывать skill ID, а не название урока, и не переиспользовать v1 snapshot/hints другого lesson.
3. **Spec-tracer после каждой серии:** проверить lesson → primary skill → транзитивное prerequisite closure, check, exercise version/snapshot и отсутствие legacy bypass.
4. **Tester:** проверить path/plan/curriculum на одном resolver, отсутствие циклов и недоступность урока без prerequisite. UI и dashboard могут показывать только фактический status из API, без выдуманных процентов.

До выполнения runtime и compatibility tests Gate A/B authoring считается **blocked**. После них content-author может писать только новые IDs по expanded contract; существующие v1 разрешены только как immutable legacy exceptions. Никаких изменений `PASS_SCORE`, mastery formula, Runner или исторических authored IDs.
## Серии авторинга (по 4 урока)

- **A — фундамент:** 1–4 (существующие 1 и 3 сохранить; добавить data types между ними и loops после conditions).
- **B — функции:** 5–8 (functions → parameters → return values → scope).
- **C — значения и логика:** 9–12 (mutability → strings → numbers → booleans).
- **D — коллекции:** 13–16 (truthiness → comprehensions → lists → tuples).

После каждой серии проверить lesson → primary skill → closure prerequisite; существование ключа check; уникальность public ID/version; реальную достижимость урока в плане и через `accessible_lesson`. Не менять `PASS_SCORE`/mastery. Каждый пример должен быть проверен как запускаемый фрагмент с точным выводом; при этом не включать выполнение кода ученика.

## Риски / вопросы авторам перед стартом

1. **Блокирующий mapping gap:** описан выше; иначе ученики обойдут data-types, а новые тесты такого порядка будут падать.
2. **План и path — разные resolver-политики:** проверить семантически, что masteried prerequisite не приводит к рекомендованному, но недоступному уроку. Не обещать всем одну и ту же последовательность при adaptive sorting.
3. **Текущая lesson-схема имеет одно primary `skill_id`:** не объединять два graph skills ради вмещения ещё четырёх узлов в 16 уроков. Completion через дополнительные `LessonSkill` links может открыть последующие узлы, а knowledge check/evidence записывается для primary skill.
4. **Объяснения вариантов:** существующий формат `CHECKS` хранит один `explanation` на вопрос, не отдельное объяснение на каждый distractor. Если для новой волны обязательно пояснение каждого варианта, это отдельное изменение контракта/схемы; пока написать содержательное объяснение вопроса без ложного обещания per-choice feedback.
5. **Mutability до формального урока lists:** примеры должны показать alias/rebinding, но дозировать list API; согласовать, допустимо ли короткое ознакомительное упоминание списка до `lists-v1`.
6. **Подсказки и версии:** levels 1–4 не раскрывают ответ; level 5 — явное решение. Старый опубликованный snapshot неизменяем; все новые lesson/check IDs должны иметь ровно соответствующий exercise ID/version, не переиспользовать чужие ladders.
7. **Следующий охват:** чтобы действительно дойти по линейному prerequisite-графу примерно до 20-го узла, нужна следующая серия `sets-v1`, `dictionaries-v1`, `slicing-v1`, `iteration-v1` после tuples; до неё не ставить исключения или backend skills в этот маршрут.

## Файлы, сверенные для этого проектирования

- `AGENTS.md`; `.agents/skills/task-router/SKILL.md`, `.agents/skills/content-authoring/SKILL.md`, `.agents/skills/learning-domain/SKILL.md`.
- `docs/decisions.md`.
- `apps/api/app/skill_graph.py`, `learning_content.py`, `knowledge_check_content.py`, `curriculum.py`, `learning.py`, `learning_plan.py`.
