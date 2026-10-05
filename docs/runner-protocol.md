# Private Python Runner protocol

Статус: архитектурный контракт Prompt 07.
Область: только граница `API → private runner worker`; этот документ не включает
реализацию worker, sandbox или API-клиента.

## 1. Решение и границы

### Факты спецификации и репозитория

- Разделы 35–41 спецификации требуют отдельную короткоживущую sandbox-среду
  на каждый запуск, лимиты ресурсов, отключённую сеть и отсутствие запуска
  пользовательского кода в API-процессе.
- Текущий `apps/api/app/runner.py` намеренно fail-closed: он не исполняет код и
  поднимает `RunnerUnavailable`.
- Текущая web/API схема не является worker-протоколом. Web не должен обращаться
  к worker напрямую.
- Новый `CodingAttempt` сохраняет FK на точную `ExerciseVersion`, а
  `idempotency_key` результата равен UUID сохранённой попытки. Нормализованный
  результат сохраняется в `submission_results`, связанном с попыткой и той же
  версией. Старые попытки и результаты без доверенной версии остаются
  nullable legacy rows и не могут быть отправлены worker-у или использованы
  для evidence.
- `record_evidence` принимает `coding_attempt` только для уже сохранённого
  protocol-validated terminal result. Он сам проверяет ownership,
  attempt/result/version identity, получает primary `skill_id` только из
  immutable `ExerciseVersion.content_snapshot`, считает score из bounded
  `tests_passed/tests_total` и получает assistance из `HintReveal` того же
  пользователя и exact version до `SubmissionResult.created_at`.
- Текущий `docker-compose.yml` не подключает runtime socket к API/web и не
  содержит worker. Это факт конфигурации, а не доказательство работающей
  изоляции.

### Варианты и последствия

| Вариант | Последствие | Решение |
|---|---|---|
| Запуск в API или локальный fallback | Код получает границу доверия основного приложения | Запрещён принятыми решениями |
| Приватный worker с durable журналом и bounded HTTP-вызовом | Одна граница исполнения, без нового брокера; неизвестный исход может навсегда потерять результат | Рекомендуется |
| Брокер, scheduler и несколько worker nodes из общей схемы §35 | Больше компонентов; доставка «хотя бы раз» всё равно требует at-most-once защиты запуска | Отложено до измеренной необходимости |

Private endpoint, форматы ниже, HTTP-коды и конкретные лимиты — предлагаемые
решения этого контракта, а не уже реализованные возможности. Разделы 37–39
описывают другие языки и preview; они намеренно вне Python MVP. Rubric и полный
поток evidence из §§40–41 здесь не включаются.

### Рекомендуемый вариант

Один приватный HTTP(S) endpoint worker-а за внутренней сетью:

```text
Browser/Web
    │  обычный authenticated API
    ▼
API modular monolith ── private mTLS/service-auth ──► Python Runner worker
                                                       │
                                                       ▼
                                               one sandbox per run
```

API остаётся владельцем пользовательской сессии, `CodingAttempt`, результата и
решения о том, какие упражнения доступны. Worker — единственный компонент,
который может обращаться к container/runtime API. Web и API не получают
runtime socket, Docker socket, host mounts или credentials worker-а.

Очередь или брокер не входят в MVP-контракт. Синхронный private endpoint
достаточен для первого worker-а; если измеренные таймауты потребуют
асинхронности, отдельный polling endpoint потребует отдельного контракта.
В version 1 повторный `POST` с неизменным key/body служит чтением уже
существующего состояния, а не командой повторного исполнения.

## 2. Endpoint и транспорт

### Endpoint

```text
POST /internal/v1/runner/executions
```

Endpoint:

- доступен только из private network;
- не публикуется через browser-facing ingress;
- требует mTLS или эквивалентной взаимной аутентификации service-to-service;
- проверяет allowlist вызывающего API и versioned protocol;
- не принимает произвольные команды, image, test paths, environment variables
  или network settings от вызывающей стороны.

Идемпотентность передаётся заголовком:

```text
Idempotency-Key: <opaque key>
```

API генерирует один ключ на сохранённую попытку, а не на HTTP-вызов. Worker
принимает 1–128 символов из `[A-Za-z0-9_-]`; UUID без разделителей подходит.
Worker не должен писать ключ целиком в обычные логи, если для
диагностики достаточно его безопасного digest.

### Request

```json
{
  "protocol_version": 1,
  "exercise_id": "variables-v1",
  "exercise_version": 1,
  "language": "python",
  "source": "def solve(value):\n    return value + 1\n",
  "mode": "function"
}
```

Обязательные поля:

| Поле | Тип и ограничения | Значение |
|---|---|---|
| `protocol_version` | integer, сейчас `1` | Версия wire-контракта |
| `exercise_id` | opaque string, 1–80 символов | Стабильный ID authored exercise; не путь |
| `exercise_version` | integer `>= 1` | Неизменяемая версия задания и его test bundle |
| `language` | allowlist, для MVP только `python` | Язык runner-а |
| `source` | UTF-8 string, 1–20 000 символов и не более 80 KiB | Код ученика; всегда недоверенный |
| `mode` | allowlist, для MVP только `function` | Разрешённый режим запуска |

Worker сам разрешает пару `(exercise_id, exercise_version)` в опубликованный
test bundle. `source` не может выбрать тесты, hidden-test source, image,
команду запуска, импорты, лимиты или переменные окружения. Неизвестные поля
отклоняются, а не игнорируются.

До создания sandbox worker валидирует:

1. protocol version, заголовок и request size;
2. allowlist exercise/version/language/mode;
3. UTF-8 и лимит исходного текста;
4. соответствие idempotency key ранее зафиксированному request digest.

Невалидный запрос не исполняется и не считается успешной попыткой.

## 3. Response

Успешно обработанный запрос возвращает JSON с нормализованным результатом:

```json
{
  "protocol_version": 1,
  "idempotency_key": "api-generated-opaque-key",
  "status": "finished",
  "tests_passed": 7,
  "tests_total": 10,
  "timeout": false,
  "resource_violation": false,
  "stdout": "...\n",
  "stderr": "",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "exit_code": 1,
  "error_code": null,
  "message": null
}
```

Обязательные result-поля:

| Поле | Тип | Семантика |
|---|---|---|
| `status` | enum | Нормализованный итог, см. ниже |
| `tests_passed` | integer `0..10 000` | Число пройденных доступных тестов |
| `tests_total` | integer `0..10 000` | Общее число доступных тестов |
| `timeout` | boolean | Сработал wall-clock timeout |
| `resource_violation` | boolean | Нарушен CPU, memory, PID, disk или output limit |
| `stdout` | bounded UTF-8 string | Захваченный stdout, с применённым лимитом |
| `stderr` | bounded UTF-8 string | Захваченный stderr, с применённым лимитом |

Все поля примера обязательны в wire-response; `exit_code` — integer или null,
`error_code`/`message` — безопасные bounded строки или null. Неизвестные поля
и неподдерживаемые enum значения отклоняются API; числа — строгие integer, не
boolean. Stack
traces, секреты, host paths, hidden-test source и внутренние credentials в
response запрещены.

`stdout`/`stderr` ограничиваются по байтам. При превышении output limit worker
обрезает данные, не блокирует API и выставляет `resource_violation=true`;
соответствующий `*_truncated=true`. Обрезание выполняется по границе UTF-8.

Всегда `0 <= tests_passed <= tests_total`. `tests_total` берётся из pinned
bundle, а не stdout/pytest-текста ученика; незапущенные тесты не считаются
пройденными. Если trustworthy counts отсутствуют, оба счётчика равны нулю и
`status` не может быть `finished`. Ноль тестов не означает успешную проверку.
Worker-статус `finished` отличается от текущих API-статусов `passed/failed`;
будущему адаптеру нужен явный mapping, не слепая запись wire JSON.

### Status enum

| `status` | Когда используется | Это успех? |
|---|---|---|
| `finished` | Sandbox завершён штатно; тесты могут быть частично или полностью пройдены | Только объективный результат, не обязательно pass |
| `timeout` | Достигнут wall-clock limit | Нет |
| `resource_violation` | Sandbox остановлен из-за CPU/memory/PID/disk/output/policy limit | Нет |
| `error` | Worker принял запуск, но pipeline завершился внутренней ошибкой | Нет |
| `unavailable` | Worker не может принять/подтвердить выполнение | Нет |
| `in_progress` | Для того же ключа уже есть активная попытка | Не финальный результат |

Для `finished/error/unavailable/in_progress` оба флага false; для `timeout`
`timeout=true, resource_violation=false`; для `resource_violation` обязательно
`resource_violation=true`. `in_progress` не содержит частичного успеха:
`tests_passed=0`, вывод пустой, `exit_code=null`.

`timeout` и `resource_violation` отражают факты независимо. Если оба флага
истинны, `status` должен быть `resource_violation`, а оба флага сохраняются.
Тестовый fail при штатном завершении — это `finished`, а не `error`.

## 4. Идемпотентность и правило «никогда дважды»

Требование протокола: один и тот же `Idempotency-Key` **никогда не приводит к
двум исполнениям кода**.

Worker обязан иметь durable idempotency record, минимум с такими данными:

```text
key
request_digest / authenticated_owner
resolved_bundle_digest / policy_revision
state: claimed | running | terminal
normalized_response
created_at / updated_at
```

Алгоритм:

1. До создания sandbox worker атомарно и durable создаёт `claimed` record с
   глобально уникальным ключом и digest канонического request. Digest включает
   все поля body, в том числе точный source без нормализации whitespace.
   Bundle digest и trusted policy revision фиксируются при claim: новая
   публикация не меняет уже принятую попытку. Доступ к чужому ключу запрещён.
2. Только владелец успешного claim может единожды durable зафиксировать
   `running` перед единственным обращением к runtime create/start. Worker не
   повторяет неоднозначный runtime create/start после сбоя. Потеря ответа
   runtime тоже сжигает право запуска, даже если sandbox реально не стартовал.
3. Повторный запрос с тем же ключом и тем же digest:
   - при `terminal` возвращает сохранённые значения response без пересчёта
     (исключение — явно описанная ниже retention policy);
   - при активном `claimed`/`running` возвращает `in_progress` и **не** создаёт
     второй sandbox.
4. Тот же ключ с другим digest отклоняется как
   `idempotency_key_reused` (`409`); новый source или версия не запускаются.
5. Если worker перезапустился после claim и не может доказать наличие
   сохранённого terminal response, он ищет и останавливает связанный sandbox,
   а запись переводит в terminal `unavailable` с
   `error_code=execution_outcome_unknown`. Повторный запрос получает этот
   результат; запуск заново запрещён. При неподтверждённом cleanup worker
   изолируется от новых admission и подаёт безопасный operational alert.

Claim, конкурентная уникальность и terminal result должны переживать restart,
deployment и ротацию credentials. In-memory cache/TTL-lock, expired lease и
повторная доставка не дают права исполнить код заново. Результат можно удалить
по retention policy, но бессрочный минимальный tombstone ключа/дайджеста должен
остаться: удалённый результат возвращает `unavailable/result_expired`, а не
новый запуск. Restore из backup, потерявшего claims, и потеря журнала требуют
fail-closed admission; нельзя продолжать с пустой или устаревшей таблицей.
Связанный с журналом runtime также не должен автоматически рестартовать
sandbox или повторять learner process.

Это **at-most-once**, не обещание exactly-once delivery или гарантированного
получения результата. Все конкурирующие процессы разделяют одну атомарную
границу claim; добавление replicas без неё запрещено.

Последний пункт намеренно жертвует liveness ради at-most-once execution:
неизвестный результат нельзя «безопасно» повторить. API также не должен
повторять запрос под новым ключом после transport timeout. Он повторяет только
тот же ключ либо оставляет попытку `unavailable`.

Два разных ключа означают две разные попытки и могут исполниться дважды. API
должен выдавать новый ключ только для явного нового submission пользователя.
«Одно исполнение» означает один запуск pipeline/sandbox для submission, не
одно обращение к learner-функции: test suite может вызывать её несколько раз.

## 5. HTTP и отказоустойчивость

### HTTP semantics

| HTTP | Условие | Исполнение |
|---:|---|---|
| `200` | terminal normalized response или повтор terminal key | Не более одного |
| `202` | запрос принят, результат ещё `in_progress` | Уже claim-нутый key |
| `400/422` | malformed/неразрешённые поля | Не выполняется |
| `401/403` | неверная service-auth или protocol permission | Не выполняется |
| `409` | тот же key с другим request digest | Не выполняется |
| `429` | worker quota/rate limit до claim | Не выполняется |
| `503` | worker unavailable до принятия запроса | Неизвестно, но новый запуск не допускается API без того же key |
| `500` | transport/server failure | API не делает retry с новым key |

Для `202`, `503` и `500` API не должен делать вывод, что код точно не
исполнялся. Безопасный retry — только с тем же ключом. Если после повторной
проверки результат нельзя получить, `CodingAttempt` сохраняется как
`unavailable`; это не pass, не evidence успеха и не основание для обновления
mastery.

В version 1: `202` возвращает ту же полную схему с `status=in_progress`;
worker-`503` до claim — схему с `status=unavailable` и
`error_code=worker_not_ready`. `400/422/401/403/409/429` используют отдельную
bounded схему `{"error_code": "...", "message": "..."}`, без результатов тестов.
Неавторизованному caller не раскрывается наличие ключа. Потеря сети или
некорректный response не являются ответом worker: API самостоятельно
нормализует `unavailable` и сохраняет неизвестность исполнения.

### Нормализация ошибок

- **Request validation error**: ошибка до sandbox; не является результатом
  тестов.
- **Worker internal error** после claim: `200` с `status=error`, безопасным
  `error_code` и `tests_passed/tests_total` по доступным данным; stack trace
  остаётся в защищённой диагностике.
- **Timeout**: worker уничтожает sandbox и возвращает `status=timeout`,
  `timeout=true`; код не повторяется автоматически.
- **Resource violation**: worker уничтожает sandbox и возвращает
  `status=resource_violation`, `resource_violation=true`.
- **Unavailable**: API не получил подтверждённый terminal result. Попытка
  остаётся `unavailable`; нельзя считать это подтверждённым завершением, pass
  или mastery evidence. Фактическое исполнение при потере связи неизвестно.

Learner wall-clock timeout не равен timeout HTTP-клиента. Первый подтверждается
worker и флагом `timeout=true`; второй означает только неизвестный исход и
`unavailable/worker_transport_timeout`. Будущий адаптер не должен использовать
нынешнюю ветку `practice.py: TimeoutError → timeout` для transport timeout.
Текущий `RunnerError → unavailable` также не является mapping нового
worker-`error`. В этой задаче обе ветки остаются неизменными.

Все terminal responses, включая `error`, `timeout`, `resource_violation` и
`unavailable`, должны быть безопасны для повторного чтения по тому же ключу.
Worker-`503` до claim и API-синтезированный `unavailable` при потере связи —
не durable terminal records worker-а; тот же ключ может позже получить
подтверждённое состояние. Это не даёт права запускать уже claimed key вновь.

## 6. Trust boundary и sandbox obligations

### Недоверенные данные

Недоверенными считаются browser input, API payload, `source`, любые тексты
упражнения/README и stdout/stderr. Они не являются инструкциями для API или
worker и не могут переопределить policy. Даже authenticated API вызывающий
рассматривается worker-ом как ограниченный caller, а не как источник
произвольных команд.

Обычные логи содержат только безопасные codes, durations, счётчики и
корреляцию. Source, stdout/stderr, payload, user email, authorization headers,
ключи и сертификаты не логируются. Protected diagnostics также требуют
redaction; доступ к ним не делает допустимой запись секретов или hidden source.

### Обязательства worker/sandbox до включения исполнения

На каждый запуск worker создаёт отдельную ephemeral sandbox и гарантирует:

- network off по умолчанию, без DNS/egress;
- non-root user;
- read-only base filesystem и отдельный временный writable directory;
- отсутствие host filesystem mounts, production secrets, API/AI keys и Docker
  socket внутри sandbox;
- hard limits для memory, CPU, PID/process count, wall-clock, disk и output;
- allowlist base images, runtime commands, test bundles и exercise versions;
- cleanup после normal completion, timeout, cancellation, worker crash и
  resource violation;
- hidden tests запускаются worker-ом, но их source никогда не возвращается
  клиенту.

Простой запуск hidden pytest рядом с learner code не доказывает сокрытие
тестов или достоверность counts: Python может читать файлы и подделывать вывод.
Trusted harness должен быть вне learner security boundary и проверять
результаты независимо. Hidden-test source, ожидаемые значения, assertion
traceback и их captured output не попадают в публичный вывод. Если такой
границы нет, deployment блокируется; фильтрация нескольких строк не заменяет
изоляцию. Raw stdout/stderr от hidden фаз не пересылаются в браузер.

Предлагаемый bounded профиль `python-function-v1` (не факт спецификации):
wall-clock 5 s, CPU budget 2 s с отдельной quota не более 1 CPU, memory
256 MiB, PID 32, writable disk 16 MiB, stdout/stderr по 16 KiB.
Request body — максимум 128 KiB; worker response — максимум 256 KiB,
`message` — 512 символов. Полные времена admission/cleanup также ограничены:
worker HTTP budget 15 s, API read deadline 20 s. Профиль должен быть
подтверждён для authored bundles перед включением; лимиты не могут быть
переопределены браузером, source или AI. Отсутствие любого enforceable limit
означает `unavailable`, а не best-effort запуск.

Скомпрометированный worker не должен автоматически получать доступ к основной
БД, secret store или AI Gateway. Worker-host — отдельная security boundary;
его service credentials ограничиваются минимально необходимыми правами и
ротируются вне пользовательского протокола.

## 7. API/web integration rules

1. Browser вызывает только обычный API endpoint и не знает private worker
   address, service credentials или idempotency implementation.
2. API валидирует ownership/access к `exercise_id` и точной опубликованной
   `exercise_version`, сохраняет source как недоверенные данные и вызывает
   worker только через этот private contract.
3. API не исполняет Python как fallback. При отсутствии worker используется
   текущий fail-closed путь `unavailable`.
4. API сохраняет normalized result в истории `CodingAttempt` и в
   `submission_results`, связанном с точной версией и idempotency key; terminal
   `unavailable`, `error`, `timeout` и `resource_violation` не превращаются в
   успешное mastery evidence.
5. Результат runner не даёт клиенту hidden-test source, внутренние пути,
   stack traces, secrets или решение упражнения.
6. Любое изменение wire-полей/семантики требует новой `protocol_version`.
7. Worker не обращается к AI Gateway и не начисляет AI usage или mastery.
   Будущий tutor feedback проходит через существующий Gateway и отдельно
   валидируемую схему. Недоверенный runner output не становится инструкцией AI.
8. Только server-side bridge из сохранённого trustworthy terminal result
   разрешает `SkillEvidence(source_type="coding_attempt")`: client/worker не
   задают `skill_id`, `result_score`, `assisted` или `hint_count`. Assistance
   считается по distinct `HintReveal.level` exact version до результата;
   mentor-чат без `HintReveal` не является hint attribution. Unavailable,
   timeout, resource violation и protocol failure не создают evidence.

## 8. Миграция, rollback и условия включения

Миграции `0029` и `0030` фиксируют normalized result, точную версию и
idempotency key. Upgrade не backfill-ит старую историю, потому что для неё
нельзя безопасно восстановить версию; такие rows остаются fail-closed.
Downgrade `0030` обратим только пока нет version-bound rows; при наличии
такого результата миграция останавливается вместо потери версии/ключа.
Worker всё ещё выключен в текущем deployment-е и должен иметь собственный
durable журнал без credentials основной БД.

Rollback deployment-а: остановить admission, гарантировать остановку/cleanup
активных sandbox, сохранить журнал/tombstones и результаты, вернуть API к
fail-closed заглушке. Rollback не должен удалять claims, переиспользовать ключи
или replay-ить неизвестные попытки. Downgrade схемы, теряющий версии/ключи или
результаты, блокируется до отдельного сохранения данных и подтверждённого
round trip. Откат документа не включает исполнение кода.

## 9. Проверки контракта

До реализации проверяется полнота и согласованность документа с §§35–41,
`docs/decisions.md`, `runner.py`, `practice.py` и конфигурацией Compose.
Проверка текста не доказывает исполнение, transport или sandbox security.

Обязательные будущие behavioral проверки:

- exact exercise version, неизвестные поля/языки/режимы, oversized request;
- параллельные одинаковые key/body — одно обращение к runtime; иной body —
  `409`, иной caller — отказ без утечки;
- crash до/после claim, перед/после runtime start, после завершения до записи
  response; restart/lease expiry/retention/backup restore — без второго запуска;
- потеря HTTP-response и transport timeout — повтор только того же ключа,
  никакого local fallback или начисления evidence;
- schema validation, counts, ноль тестов, UTF-8 truncation, отсутствие hidden
  source/секретов/paths, learner spoofing результата;
- реальные CPU/memory/PID/disk/time/output/network ограничения, cleanup
  при timeout/cancel/crash и недоступность runtime socket из API/web/sandbox;
- отказ без authenticated private service access и ротация credentials без
  сброса журнала;
- отдельно — будущая миграция/rollback на существующих данных.

В рамках изменения документа реальный PostgreSQL, Alembic round trip,
изолированное исполнение, mTLS/private endpoint и end-to-end браузер не
проверяются. Наличие текущих stub/mock тестов не подтверждает at-most-once
или security будущего worker-а.

## 10. Не входит в этот контракт

- реализация worker;
- выбор Docker/gVisor/Firecracker;
- очередь, retry policy сверх правила «тот же key»;
- tutor feedback и rubric scoring (узкий coding-evidence bridge описан выше);
- запуск кода на текущей машине.

До отдельного security review и проверенного deployment-а worker остаётся
выключенным. Это сохраняет принятое решение проекта: Runner fail-closed.
