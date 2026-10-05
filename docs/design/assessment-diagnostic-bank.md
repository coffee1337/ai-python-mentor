# Диагностика: банк вопросов и адаптивный выбор (промт 08)

Статус: дизайн. Код этим документом не меняется.
Область: только `python.core` (42 навыка). `python.backend` — отдельная задача (промт 09).

## 0. Проверенное состояние, на которое опирается дизайн

| Что | Значение |
|---|---|
| Навыков `python.core` в `SKILLS` | 42, `difficulty` 0.1 … 0.9, шаг 0.02 |
| Вопросов в `QUESTIONS` | 6, покрывают 2 навыка (`python.variables`, `python.conditionals`) |
| `MAX_QUESTIONS` | 4 |
| `DIFFICULTY_PRIOR` | `beginner` 0.15, `student` 0.3, `junior` 0.45 |
| Уроков в `LESSONS` | 16 (только первые 16 навыков цепочки) |
| Ответ клиенту | `QuestionResponse{id,skill_id,difficulty,prompt,choices,question_number,total_questions}` — поля `answer` нет |

Ключевой разрыв: новичок проходит диагностику, `curriculum` выдаёт уроки 1–3, и после этого
диагностика больше ничего о нём не знает. Причина техническая: `UserSkill` получает ровно
одну строку evidence на затронутый навык (`source_type="assessment_response"`), поэтому после
4 вопросов навык известен с точностью «один вопрос = один факт». Curriculum при этом
ориентируется на `mastery_value` и `MASTERY_READINESS_THRESHOLD = 0.75`, а не на «покрытие».

## 1. Размер банка и `MAX_QUESTIONS`

### 1.1 Сколько вопросов нужно на 42 навыка

Минимум — 42 (по одному на навык): это нижняя граница, на которой «все 42 навыка покрыты»
формально выполняется. Но один вопрос на навык не даёт ничего, кроме факта
«знает / не знает»: единственный сигнал по навыку — один исход с двумя значениями.

Рекомендация — **2 вопроса на навык плюс 4 уже опубликованных, 88 вопросов в банке**:

- 1 вопрос/навык: покрытие есть, но ранжировать навыки внутри прогона нечем —
  `UserSkill.knowledge_score` у всех затронутых навыков при одной доле верных ответов
  одинаков, а порядок уроков решается по `gap` и `importance`.
- 2 вопроса/навык: доля 0 / 0.5 / 1 различает «не знает», «примерно понимает»,
  «уверенно знает». Этого достаточно, чтобы `UserSkill` различал «пробел» и «слабый
  навык» — то самое различие, из которого curriculum строит порядок.
- 3 вопроса/навык (126) точнее, но 126 авторских вопросов с проверенным выводом — это
  дисциплинарная цена, а `MAX_QUESTIONS = 8` всё равно не соберёт 126 сигналов за прогон.

### 1.2 Сколько задаётся за прогон

| Вариант | Время новичка (оценка) | Навыков за прогон | Комментарий |
|---|---|---|---|
| 4 (сейчас) | ~3 мин | ≤4 из 42 | практически не различает уровни; prior на 10% навыков |
| 6 | ~4–5 мин | ≤6 из 42 | верхняя граница, при которой `total_questions` не требует правок веба |
| 8 | ~6–7 мин | ≤8 из 42 | прирост времени до первого урока; визуально это всё ещё «почти ничего» |

**Рекомендация: `MAX_QUESTIONS = 6`.** Банк вырос почти в 15 раз (6 → 88), а лимит остался бы 4:
тогда адаптивная ветка почти не использует банк, и диагностика остаётся такой же бедной,
как сейчас, но дороже в поддержке. 6 — компромисс: +2 мин к входу на курс из 42 уроков
незначительно, а число затронутых навыков растёт с 4 до 6 (+50%). 8 не берём: 8 вопросов
из 42 навыков — это 19% покрытия, а прирост времени заметнее.

`MAX_QUESTIONS` читается фронтендом как `total_questions`
(`apps/web/app/assessment/page.tsx`, тип `Question`), поэтому изменение не требует правок
веба: контракт и его рендеринг уже параметризованы.

## 2. Вопрос → навык → difficulty

### 2.1 Сколько вопросов на навык

2 вопроса на навык, и они **не равнозначны по роли**:

- **anchor** — difficulty около `skill.difficulty − 0.05`. Проверяет «узнаёт ли человек
  тему вообще».
- **probe** — difficulty около `skill.difficulty + 0.07`. Проверяет «умеет ли применять».
  Именно probe отличает «знает» от «умеет».

Разница в difficulty между anchor и probe — не украшение, а различение сигнала: за прогон
с 6 вопросами обычно попадает либо один, либо оба вопроса одного навыка; если попал
только probe и ответ верен, навык крепче, чем если попал только anchor.

### 2.2 Диапазоны difficulty

`skill.difficulty` идёт с шагом 0.02 от 0.1 до 0.9, а `DIFFICULTY_PRIOR` задаёт стартовые
точки 0.15 / 0.3 / 0.45. Чтобы адаптивная ветка была осмысленной, а не случайной,
вводится одно правило: **сложность вопроса должна лежать в диапазоне навыка**, иначе
ответ ничего не говорит о навыке.

| Параметр | Значение |
|---|---|
| Диапазон anchor | `[max(0.1, skill.difficulty − 0.05), skill.difficulty]` |
| Диапазон probe | `[skill.difficulty, min(0.9, skill.difficulty + 0.07)]` |
| Разница anchor → probe | не более 0.12 |

Пример: `python.lists` (skill.difficulty 0.38) → anchor 0.33–0.38, probe 0.38–0.45.
Ни один вопрос не «перескакивает» на соседний навык: `python.dictionaries` (0.44)
начинается с 0.44, и probe списков (максимум 0.45) может пересечься с ним численно,
но не по смыслу — вопрос про изменение списка не оценивается как «знает словари».

### 2.3 Траектории

**Новичок (`beginner`, prior 0.15).** Старт: ближайший к 0.15 anchor →
`python.variables` (difficulty 0.15 у legacy-вопроса `variables-v1`, разница 0.0) —
это совпадает с текущим поведением, которое уже проверено тестом.

Три правильных ответа подряд при текущем шаге `+0.2` дают 0.15 → 0.35 → 0.55 → 0.75,
то есть новичок за один прогон проверяется на `scope`/`strings` и выше. Это неверно:
новичок не должен за один прогон проверяться на `classes`.

Поэтому шаг `+0.2` заменяется на шаг, привязанный к слотам графа:

```
SLOT_STEP = 0.10   # шаг по «слотам» skill.difficulty
```

`target = min(0.9, current_slot + SLOT_STEP)` при верном ответе и
`max(0.1, current_slot − 0.10)` при неверном, где `current_slot` — ближайший
`skill.difficulty` к difficulty текущего вопроса. Итог для новичка: 0.10 → 0.20 → 0.30 →
0.40, то есть `variables → conditionals/loops → functions/parameters`, а не `classes`.
Четыре ответа дают уровень примерно 4–5 уроков — это ровно тот порядок, который
curriculum выдаст дальше, и он согласован с `DIFFICULTY_PRIOR` для `beginner`.

**Junior (`junior`, prior 0.45).** Старт со слота 0.44–0.46 → anchor
`python.dictionaries` или `python.slicing`. Две ошибки подряд: 0.44 → 0.34 → 0.24,
то есть откат к `python.strings` / `python.mutability`. Это осмысленно: не «случайно
ниже», а «проверяем фундамент, на котором junior ошибся».

## 3. Предотвращение утечки ответа

Текущая защиза уже соблюдается и не должна ломаться:

1. `QuestionResponse` не содержит `answer` и остаётся единственным объектом,
   возвращаемым в `GET /assessment` и в `state.question`.
2. Ответ клиента — строка из `choices`; `payload.answer not in q["choices"]` → 422,
   сравнение `payload.answer == q["answer"]` делается на сервере.
3. `answer` попадает в `AssessmentResponse.answer` и в `content_snapshot` — оба серверные.
4. `POST /assessment/answers` отвечает `{correct, feedback, state}`; `correct` —
   вычисленный факт по уже отправленному ответу, а не раскрытие ключа для ещё
   не заданного вопроса.

Чем плоха эвристика «сложность вопроса»: если бы сложность была функцией от правильного
ответа (например, один «лёгкий» и один «трудный» вариант ответа в одном вопросе), то
клиент, увидев сложность, получал бы ответ. Поэтому:

- у вопроса ровно **одна** шкала сложности, не зависящая от выбора ученика;
- варианты ответа не различаются по длине так, что правильный заметно отличается;
- уровень 5 лестницы подсказок — это `solution`: он раскрывает эталонное решение и не
  даёт самостоятельного кредита (`derive_assistance` → `assisted=True`). Это другой
  механизм, чем утечка ключа вопроса: подсказка раскрывает авторский ответ, но не ответ
  на *текущий* диагностический вопрос, потому что диагностические вопросы не имеют
  hint ladder.

Вывод: расширение банка не должно добавлять полей в `QuestionResponse` и не должно
публиковать `difficulty` как производное от правильности ответа (у нас `difficulty` —
свойство вопроса, а не ответа, поэтому это безопасно).

## 4. Алгоритм «ответил → следующий вопрос»

### 4.1 Старт прогона

```
prior = DIFFICULTY_PRIOR.get(profile.experience_level, 0.15)   # 0.15 / 0.3 / 0.45
candidates = [q for q in BANK if q.id not in asked]
q = argmin(candidates, key=lambda q: (abs(q.difficulty - prior), q.skill_order, q.id))
```

Ключ сортировки из трёх компонентов: близость к prior, порядок навыка в графе, `id`.
Последний компонент делает выбор детерминированным — без него при равенстве расстояния
выбор зависел бы от порядка кортежа.

### 4.2 Переход после ответа

```
answer_ok   = (submitted == correct_answer)               # серверная проверка
slot        = nearest_skill_slot(current_question.difficulty)
next_slot   = min(0.9, slot + 0.10) if answer_ok else max(0.1, slot - 0.10)

pool = [q for q in BANK
        if q.id not in asked
        and q.skill_id != current_question.skill_id]      # не повторять навык подряд
near = [q for q in pool if abs(q.difficulty - next_slot) <= 0.02]
if not near:
    near = [q for q in pool if abs(q.difficulty - next_slot) <= 0.10]   # резервный коридор
if not near:
    next = None                                            # кандидатов нет
else:
    next = argmin(near, key=lambda q: (abs(q.difficulty - next_slot), q.skill_order, q.id))

ранняя остановка: answered >= MAX_QUESTIONS  ->  run.status = "completed"
                 next is None                 ->  run.status = "completed"
```

Таблица переходов:

| Ответ | `next_slot` | Что попадёт в прогон | Комментарий |
|---|---|---|---|
| верный, slot 0.10 | 0.20 | anchor `conditionals` / `loops` | +1 слот, «ещё чуть сложнее» |
| верный, slot 0.40 | 0.50 | probe `exceptions` / `try_except` | переход на следующий блок |
| неверный, slot 0.50 | 0.40 | probe `lists` / `tuples` | спуск, но не дно |
| неверный, slot 0.10 | 0.10 | anchor `variables` / `data_types` | дно: дальше некуда |
| кандидатов нет | — | — | прогон завершается досрочно |

### 4.3 Что остаётся как есть

- `current_question_id` / `current_exercise_version_id` очищаются при завершении —
  иначе `_state` читал бы снапшот закрытого вопроса.
- `asked_question_ids` — единственный источник «что уже спрошено»; он же даёт защиту
  от повторов и от `UniqueConstraint("uq_assessment_run_question")`.
- Адаптивный выбор не влияет на формулу mastery и не ослабляет `PASS_SCORE = 0.75`
  в `knowledge_check.py`: диагностика — prior, а не проверка прохождения урока.

## 5. Поведение при слабом результате

Требование: диагностика — prior, а не экзамен.

- Стартовый вопрос при слабом результате — уровня `variables-v1` (anchor
  `python.variables`), а не «тест на уровень».
- Нет экрана «вы провалили тест» и нет сообщения об ошибке: `AnswerResponse.feedback`
  при неверном ответе — нейтральное «Ответ неверный; следующий вопрос подскажет
  направление», а `state.completed` даёт `score` как долю верных ответов этого прогона.
- `score` — доля верных ответов в прогоне, а не уровень ученика. Формулировка
  «Правильный ответ: N%» в вебе описывает прогон и не должна превращаться
  в «у вас уровень X%».
- После завершения прогона `generate_plan` и `build_curriculum` строят план. При слабом
  результате `python.variables` — корень prerequisite-closure, поэтому
  `is_skill_ready` для него истинно и curriculum начинает с `variables-v1`.
  Корректный старт обеспечивается существующей логикой prerequisites, дополнительных
  экранов не требуется.
- Ничего не блокируется: диагностика не влияет на доступ к урокам и не создаёт
  отрицательную evidence. `UserSkill` получает строки только за фактически заданные
  вопросы.

## 6. Fail-closed валидация банка

Валидация выполняется на импорте `app.assessment_content` (то есть при старте процесса),
по образцу `validate_graph()` в `skill_graph.py` и `validate_hint_ladders()` в
`learning_content.py`.

| # | Проверка | Реакция |
|---|---|---|
| 1 | `id` — непустая строка, уникальна, заканчивается на `-v1` | `ValueError` |
| 2 | `skill_id` существует в `SKILLS` | `ValueError` |
| 3 | `SKILLS[skill_id].category == "python.core"` | `ValueError` |
| 4 | `prompt` — непустая строка | `ValueError` |
| 5 | `choices` — непустой список уникальных непустых строк | `ValueError` |
| 6 | `answer` ∈ `choices` | `ValueError` |
| 7 | `difficulty` — число в `[0.1, 0.9]` | `ValueError` |
| 8 | `difficulty` попадает в диапазон anchor/probe своего навыка | `ValueError` |
| 9 | каждый навык `python.core` покрыт хотя бы одним вопросом | `ValueError` |

Пункт 9 — самый важный для цели промта: «вопрос без навыка в графе не должен попасть в
банк» и «все 42 навыка покрыты» проверяются на старте, а не тестом в CI. Fail-closed
означает: процесс не поднимается с невалидным банком, а не «молча пропускает плохой
вопрос».

Дополнительно на уровне сервиса: `_snapshot_question` в `assessment.py` уже проверяет
принадлежность `answer` к `choices` и соответствие `question["id"]` версии упражнения,
поэтому испорченный снапшот даёт 409, а не утечку.

## 7. Миграция с текущих 6 вопросов

Инвариант: публичные ID авторского контента неизменяемы. Поэтому:

| Действие | Детали |
|---|---|
| Сохранить без изменений | `variables-v1`, `types-v1`, `conditions-v1`, `boolean-v1`, `assignment-v1`, `branch-v1` — ID, тексты, `answer`, `difficulty` |
| Добавить | 82 новых вопроса с ID вида `<skill-slug>-<probe|anchor>-v1` |
| Изменить | `MAX_QUESTIONS` 4 → 6 |
| Итог | 88 вопросов: 2 навыка по 4 (legacy + anchor/probe), 40 навыков по 2 |
| Не менять | формулу mastery, `PASS_SCORE`, контракт `QuestionResponse`, `DIFFICULTY_PRIOR` |

Проблема существующих 6: их `difficulty` не соответствует правилу диапазона.
`types-v1` = 0.25 при `python.variables` (skill.difficulty 0.10), `boolean-v1` = 0.45,
`assignment-v1` = 0.55, `branch-v1` = 0.65 — все вне anchor-диапазона своего навыка.

**Решение:** legacy-вопросы исключаются из правила №8 (список
`_LEGACY_DIFFICULTY_EXEMPT` рядом с существующим `_LEGACY_SCHEMA_ONE_CHECKS` в
`exercise_snapshots.py`), но участвуют в правилах №1–№7 и №9. Это сохраняет их
неизменность и одновременно включает валидацию всего остального — тот же подход, что
уже применён к schema-1 проверкам.

## 8. Таблица «навык → question id → difficulty»

Формат: `anchor-difficulty / probe-difficulty`. Значения — рекомендуемые; автор может
сдвинуть на ±0.02, не выходя из диапазона раздела 2.2.

| # | skill | skill.difficulty | anchor id | anchor | probe id | probe |
|---|---|---|---|---|---|---|
| 1 | python.variables | 0.10 | `variables-reassign-v1` | 0.10 | `types-v1` *(legacy)* | 0.25 |
| 2 | python.data_types | 0.12 | `data-types-cast-v1` | 0.10 | `data-types-convert-v1` | 0.16 |
| 3 | python.conditionals | 0.14 | `conditions-chain-v1` | 0.20 | `conditions-v1` *(legacy)* | 0.35 |
| 4 | python.loops | 0.16 | `loops-range-v1` | 0.16 | `loops-accumulate-v1` | 0.22 |
| 5 | python.functions | 0.18 | `functions-call-v1` | 0.18 | `functions-default-flow-v1` | 0.24 |
| 6 | python.parameters | 0.20 | `parameters-args-v1` | 0.20 | `parameters-kwargs-v1` | 0.26 |
| 7 | python.return_values | 0.22 | `return-values-implicit-v1` | 0.22 | `return-values-tuple-v1` | 0.28 |
| 8 | python.scope | 0.24 | `scope-global-read-v1` | 0.24 | `scope-name-error-v1` | 0.30 |
| 9 | python.mutability | 0.26 | `mutability-list-shared-v1` | 0.26 | `mutability-copy-v1` | 0.32 |
| 10 | python.strings | 0.28 | `strings-index-v1` | 0.28 | `strings-slice-v1` | 0.34 |
| 11 | python.numbers | 0.30 | `numbers-int-division-v1` | 0.30 | `numbers-round-v1` | 0.36 |
| 12 | python.booleans | 0.32 | `booleans-comparison-v1` | 0.32 | `booleans-chain-v1` | 0.38 |
| 13 | python.truthiness | 0.34 | `truthiness-empty-v1` | 0.34 | `truthiness-custom-v1` | 0.40 |
| 14 | python.comprehensions | 0.36 | `comprehensions-basic-v1` | 0.36 | `comprehensions-conditional-v1` | 0.42 |
| 15 | python.lists | 0.38 | `lists-append-v1` | 0.38 | `lists-mutate-v1` | 0.44 |
| 16 | python.tuples | 0.40 | `tuples-unpack-v1` | 0.40 | `tuples-immutable-v1` | 0.46 |
| 17 | python.sets | 0.42 | `sets-membership-v1` | 0.42 | `sets-dedupe-v1` | 0.48 |
| 18 | python.dictionaries | 0.44 | `dictionaries-key-v1` | 0.44 | `dictionaries-default-v1` | 0.50 |
| 19 | python.slicing | 0.46 | `slicing-basic-v1` | 0.46 | `slicing-negative-step-v1` | 0.52 |
| 20 | python.iteration | 0.48 | `iteration-items-v1` | 0.48 | `iteration-enumerate-v1` | 0.54 |
| 21 | python.exceptions | 0.50 | `exceptions-raise-v1` | 0.50 | `exceptions-message-v1` | 0.56 |
| 22 | python.try_except | 0.52 | `try-except-order-v1` | 0.52 | `try-except-finally-v1` | 0.58 |
| 23 | python.custom_exceptions | 0.54 | `custom-exceptions-class-v1` | 0.54 | `custom-exceptions-raise-v1` | 0.60 |
| 24 | python.modules | 0.56 | `modules-file-v1` | 0.56 | `modules-main-v1` | 0.62 |
| 25 | python.packages | 0.58 | `packages-init-v1` | 0.58 | `packages-relative-v1` | 0.64 |
| 26 | python.imports | 0.60 | `imports-alias-v1` | 0.60 | `imports-from-v1` | 0.66 |
| 27 | python.testing_basics | 0.62 | `testing-basics-assert-v1` | 0.62 | `testing-basics-failure-v1` | 0.68 |
| 28 | python.assertions | 0.64 | `assertions-usage-v1` | 0.64 | `assertions-optimized-v1` | 0.70 |
| 29 | python.pytest_basics | 0.66 | `pytest-basics-run-v1` | 0.66 | `pytest-basics-select-v1` | 0.72 |
| 30 | python.fixtures | 0.68 | `fixtures-scope-v1` | 0.68 | `fixtures-yield-v1` | 0.74 |
| 31 | python.typing_basics | 0.70 | `typing-basics-annotation-v1` | 0.70 | `typing-basics-optional-v1` | 0.76 |
| 32 | python.type_hints | 0.72 | `type-hints-signature-v1` | 0.72 | `type-hints-alias-v1` | 0.78 |
| 33 | python.dataclasses | 0.74 | `dataclasses-declare-v1` | 0.74 | `dataclasses-default-v1` | 0.80 |
| 34 | python.classes | 0.76 | `classes-init-v1` | 0.76 | `classes-method-v1` | 0.82 |
| 35 | python.objects | 0.78 | `objects-attribute-v1` | 0.78 | `objects-class-attribute-v1` | 0.84 |
| 36 | python.inheritance | 0.80 | `inheritance-override-v1` | 0.80 | `inheritance-super-v1` | 0.86 |
| 37 | python.composition | 0.82 | `composition-delegate-v1` | 0.82 | `composition-choose-v1` | 0.88 |
| 38 | python.protocols | 0.84 | `protocols-structure-v1` | 0.84 | `protocols-runtime-v1` | 0.86 |
| 39 | python.decorators | 0.86 | `decorators-wrap-v1` | 0.86 | `decorators-args-v1` | 0.88 |
| 40 | python.generators | 0.88 | `generators-yield-v1` | 0.88 | `generators-send-v1` | 0.90 |
| 41 | python.iterators | 0.90 | `iterators-next-v1` | 0.90 | `iterators-stop-v1` | 0.88 |
| 42 | python.context_managers | 0.90 | `context-managers-with-v1` | 0.88 | `context-managers-enter-v1` | 0.90 |

### 8.1 Проверка согласованности с графом

| Свойство | Как проверить |
|---|---|
| покрытие 42 навыков | `set(SKILLS where category==python.core) == set(q.skill_id for q in BANK)` |
| anchor ≤ skill.difficulty ≤ probe | для строк 2–42; строки 1 и 3 — legacy-исключения |
| difficulty ∈ [0.1, 0.9] | для всех 88 |
| уникальность `id` | `len({q.id}) == 88` |
| суффикс `-v1` | для всех 88 |

Порядок в таблице совпадает с порядком `SKILLS` в `skill_graph.py`, поэтому `skill_order`
в ключе сортировки совпадает с номером строки — переходы идут в порядке прохождения
курса, а не случайно.

## 9. Чего этот дизайн не делает

- Не добавляет hint ladder к диагностическим вопросам: у них нет практики, а подсказки
  раскрывают `solution`, что противоречит природе prior-вопроса.
- Не меняет `DIFFICULTY_PRIOR` и не вводит новые роли.
- Не меняет формулу mastery, `PASS_SCORE`, `MAX_TESTS` runner-а.
- Не трогает `python.backend`: банк валидируется по `category == "python.core"`.
- Не расширяет API: `QuestionResponse` остаётся без `answer`.

## 10. Проверяемые утверждения этого документа

| Утверждение | Где проверяется |
|---|---|
| 88 вопросов, 42 навыка, уникальные id с `-v1` | `test_diagnostic_bank_covers_every_core_skill` |
| каждый `skill_id` есть в `SKILLS` и `category == "python.core"` | `test_every_bank_question_resolves_in_the_skill_graph` |
| `answer` отсутствует в ответе API | `test_answer_never_reaches_the_client` |
| верный ответ повышает сложность следующего, неверный понижает | `test_correct_answer_raises_the_next_difficulty` и `test_branch_never_repeats_a_question_or_a_skill_back_to_back` |
| прогон останавливается на `MAX_QUESTIONS` | `test_early_stop_respects_max_questions` |
| невалидный банк не поднимет процесс | `test_bank_with_an_unknown_skill_is_rejected`, `test_bank_missing_a_core_skill_is_rejected`, `test_question_outside_its_skill_range_is_rejected` |
