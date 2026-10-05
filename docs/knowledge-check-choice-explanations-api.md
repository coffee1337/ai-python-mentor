# Knowledge-check: объяснение выбранного варианта — API decision

Статус: контракт для реализации, 4 октября 2026. Scope: только feedback CHECKS. Не меняет mastery, подсказки или Runner; не требует миграции БД.

## Решение и контракты

Сохраняются текущие маршруты и привязка одного opaque pending-сеанса к точному ExerciseVersion. GET создаёт или повторно использует pending-сеанс; POST работает только с его snapshot и потребляет сеанс лишь после успешной валидации и grading. POST не пере-разрешает текущий authored CHECKS.

### GET

GET /learning/lessons/{lesson_id}/knowledge-check использует текущую auth/access политику, без CSRF. Успешный ответ сохраняет совместимый формат:

~~~json
[{"id":"...","prompt":"...","choices":["...","..."]}]
~~~

Не выдавать answer, explanation, choice_explanations, correctness/score, ExerciseVersion/session/database IDs или иные grading данные. В частности, не раскрывать объяснения distractors до отправки ответа.

### POST

POST /learning/lessons/{lesson_id}/knowledge-check использует текущую auth и обязательную CSRF-проверку; успех остаётся 201. Входная схема остаётся строгой (extra="forbid"):

~~~json
{"answers":{"<question_id>":"<точная строка одного предложенного варианта>"}}
~~~

Клиент не передаёт и сервер отвергает дополнительные поля, в том числе explanation, selected_explanation, answer, correct, score, passed, assisted, hint_count, exercise_version_id и user/session IDs. Сервер проверяет полноту и точное соответствие question/choice snapshot, затем сам вычисляет оценку по snapshot answer key. Неправильный выбор тоже получает feedback именно для выбранной строки.

В текущем CheckResponse сохранить lesson_id, score, passed, recommendation, recommended_lesson_id и элементы explanations с question_id, общим explanation и строковым correct ("true"/"false"). Аддитивно добавить selected_explanation как optional/nullable string к каждому элементу (для schema 1 — общий explanation как fallback). Новые клиенты используют selected_explanation ?? explanation. Ответ не содержит полного map, answer key или невыбранные feedback-тексты. correct/score после POST остаются как в текущем контракте: запрет касается утечки до ответа, а не удаления результата grading.

**Backward compatibility:** request и GET-форма не меняются; POST response расширяется необязательным полем, старые клиенты сохраняют прежние поля. Это backward-compatible для клиентов, допускающих неизвестные response-поля; клиенты с exact-shape validation должны быть обновлены/согласованно версионированы до включения.

## Snapshot compatibility и публикация

- content_snapshot.schema_version = 1 остаётся допустимым legacy-форматом. Для него POST заполняет selected_explanation общим explanation вопроса как fallback.
- Новые опубликованные snapshots используют schema_version = 2; каждый check-вопрос содержит choice_explanations: {<точный choice>: <непустое объяснение>}. Для schema 2 ключи должны в точности совпадать с choices: без пропусков и лишних ключей; сами choices должны быть уникальны. Значения — непустые строки. Некорректный snapshot нельзя публиковать или выдавать.
- choice_explanations входит в immutable ExerciseVersion.content_snapshot; POST берёт его только из KnowledgeCheckSession.exercise_version_id → ExerciseVersion. Не читать текущий Python CHECKS для ответа.
- Не backfill-ить и не дописывать опубликованный JSON snapshot, даже если это «только пояснения». Создать новую ExerciseVersion и snapshot schema 2; оставить прежнюю версию неизменной. При изменении опубликованного public content следовать learning-domain: новый authored ID/version, не менять существующий *-v1 на месте. Изменение JSON-формы само по себе не требует SQL-миграции.

## Ошибки

Сохранить существующие HTTP статусы и строковый detail; для новых доменных ошибок использовать стабильный code рядом с detail, без внутренних причин и содержимого snapshot. Структурный Pydantic 422 остаётся validation error и не раскрывает grading data.

| HTTP | code | Ситуация |
|---|---|---|
| 409 | KC_PENDING_SESSION_REQUIRED | Нет pending GET-сеанса (включая уже использованный). |
| 409 | KC_SNAPSHOT_UNAVAILABLE | Связанный ExerciseVersion/snapshot отсутствует, повреждён или не проходит схему. |
| 422 | KC_INVALID_ANSWERS | Набор question IDs неполон/лишний либо выбор отсутствует в choices snapshot. Не потреблять pending-сеанс. |
| 401/403 | существующий auth/access code/status | Нет сессии, CSRF или доступа; политика без изменений. |

Ошибки не включают правильный вариант, choice_explanations, session/version IDs, SQL/provider детали. Rate limits остаются текущими; новый лимит этим контрактом не вводится.

## Обязательные regression tests

1. GET для schema 1 и 2 возвращает только публичные поля: без answer, общих/вариантных объяснений, grading-ключей и version/session IDs.
2. POST по schema 2 возвращает выбранное объяснение для правильного и неправильного ответа; при wrong choice текст взят именно из его map entry. Другие объяснения и весь map в ответ не попадают.
3. После GET изменить authored in-memory CHECKS или опубликовать следующую версию: POST всё ещё grades и объясняет по исходному pending snapshot.
4. Schema 1 использует общий explanation fallback; schema 2 отвергает snapshot с пропущенным/лишним choice key, пустым текстом или некорректным answer.
5. Клиентские explanation/grade/assistance/version/user поля дают 422; неправильные/неполные ответы не consume pending-сеанс. Без pending GET POST даёт 409; успешный POST потребляет сеанс, повторный даёт 409.
6. Новая публикация создаёт отдельную ExerciseVersion; старый snapshot структурно неизменен. Зафиксировать, что PASS_SCORE и формула mastery не меняются.

PostgreSQL migration не требуется для добавления JSON-поля. Реальная PostgreSQL и browser E2E — отдельные проверки реализации.
