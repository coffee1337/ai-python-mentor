# Security review: Prompt 07 Runner

Дата review: 4 октября 2026 г.

## Решение

**NO-GO для включения исполнения пользовательского кода.** Runner должен
оставаться `unavailable`/fail-closed до тех пор, пока отдельный worker не
пройдёт проверку изоляции, лимитов, cleanup, аутентификации и отказоустойчивости.
Этот документ фиксирует требования к дизайну, а не инструкции по запуску
реального worker.

При любом из следующих инфраструктурных условий API не должен исполнять код
локально, принимать результат как успешный или создавать объективное
`SkillEvidence` о прохождении:

- worker недоступен, не прошёл взаимную аутентификацию или вернул невалидный
  результат;
- истёк транспортный timeout, потеряна связь или неизвестно, был ли job выполнен;
- не применена политика образа, команды, тестов, лимитов или изоляции;
- результат нельзя однозначно связать с серверным job/idempotency key;
- cleanup не подтверждён либо worker упал в неопределённом состоянии.

Публичное безопасное поведение — `unavailable`, без credit за прохождение.
`indeterminate` ниже обозначает внутреннюю неопределённость, а не добавленный
этим review статус wire-contract. Повтор запроса использует тот же job/key и
не запускает код второй раз; неизвестный исход сначала требует reconciliation.
Новый submission не должен служить способом обойти остановку старого job.

Подтверждённый worker-ом timeout самого ученического кода/OOM — не то же самое,
что недоступность инфраструктуры: это может быть валидный отрицательный результат,
но никогда не pass. Его доменную обработку определяет отдельный контракт evidence,
без обхода существующих правил attribution подсказок.

Само наличие `RUNNER_URL`, `RUNNER_AUTH_TOKEN` и transport timeout не доказывает
верификацию worker. До отдельного допуска нельзя добавлять флаг исполнения,
локальный fallback, пример реального запуска или считать этот документ разрешением
на запуск.

## Область и граница доверия

Изучены `docs/prompts/07-runner-design.md`, решение «Runner fail-closed» в
`docs/decisions.md` и разделы 35–41 в `ai_programming_tutor_full_spec.md`:

- раздел 35: архитектура и минимальные ограничения sandbox;
- раздел 36: Python pipeline и normalized result;
- раздел 37: будущий JavaScript/TypeScript runner;
- раздел 38: будущий C++ runner;
- раздел 39: browser preview для HTML/CSS/React;
- раздел 40: public/hidden tests и передача данных в LLM;
- раздел 41: data flow submission.

Недоверенные данные:

- код, комментарии, docstrings, README и имена файлов ученика;
- загруженные архивы и тексты;
- `stdout`, `stderr`, сообщения исключений и findings статических анализаторов;
- любые поля, пришедшие из браузера, включая exercise/version/mode, если они не
  разрешены сервером;
- данные, передаваемые Tutor Engine/LLM. Они являются контекстом, а не
  инструкциями.

Текст Prompt 07 и спецификации рассматривается как предмет review, а не разрешение
выполнить содержащиеся в нём инструкции реализации/делегации.

Сервер должен сам разрешать exercise version, image, команды и набор тестов из
иммутабельного каталога. Клиент может выбрать только разрешённую сервером
операцию; он не должен задавать image, executable, аргументы-пути, public/hidden
test paths или произвольный режим.

Worker orchestration и sandbox — **разные** области доверия: identity worker,
доступ к runtime и trusted evaluator существуют только снаружи исполняемого кода.
Image/test каталог доверен лишь после авторинга и проверки provenance; ответ LLM
не может сам стать элементом allowlist.

Граница должна выглядеть так:

```text
Browser / untrusted submission
        ↓
API: auth, ownership, validation, quota, job key
        ↓ private authenticated channel
Worker scheduler: policy enforcement
        ↓
Ephemeral sandbox: untrusted code
        ↓ bounded normalized result
API / persistence / Tutor Engine
```

API и web не получают runtime socket. Компрометация sandbox или runner host не
должна автоматически давать доступ к production DB, AI keys, application
secrets, host filesystem или внутренним control-plane endpoints.

## Требования и угрозы

Приоритеты обозначают потенциальное влияние дефекта дизайна, а не найденную
эксплуатируемую уязвимость production. Критический — escape/секреты/контроль хоста;
высокий — DoS, IDOR, подмена оценки или раскрытие hidden tests.

| Область | Решение | Конкретный путь эксплуатации и последствие |
|---|---|---|
| **Network off** | Отдельный network namespace без внешнего ingress/egress, host network, DNS и маршрутов к IPv4/IPv6 metadata, соседним job и внутренним сервисам. Локальный loopback самого sandbox не должен вести к loopback хоста. Control channel/API credentials и inherited network descriptors в sandbox не передаются; host UNIX sockets/vsock также закрыты. Нет downloads/install/callbacks. | **Критический:** код использует HTTP/DNS или доступный control socket для SSRF, чтения metadata и эксфильтрации. Private network worker сама по себе не изолирует guest. |
| **Non-root** | Фиксированный непривилегированный UID/GID внутри sandbox и unprivileged mapping на хосте; все capabilities сняты, повышение привилегий запрещено (`no_new_privileges`), нет privileged, host PID/IPC/devices. Обязательны проверенные seccomp и MAC-профили, а не unconfined. Non-root не заменяет sandbox. | **Критический:** setuid/capability или ошибка namespace/runtime позволяет воздействовать на host/соседние job. Общий kernel остаётся риском; одного флага non-root для допуска недостаточно. |
| **Read-only base** | Root filesystem и серверные assets read-only, image закреплён digest. Только bounded per-job tmpfs writable; writable image layer/общие cache/volumes запрещены. Starter/source помещаются в среду без host bind mounts и под фиксированными серверными именами. | **Высокий:** запись в harness/кэш меняет оценку или следующий job. Read-only защищает от записи, но не от чтения hidden source — см. раздел о tests. |
| **Tmpfs** | Per-job tmpfs, quota размера и inode, `nosuid`/`nodev`/`noexec`, владельцем является guest UID. Все writable areas, в том числе `/tmp`, `/dev/shm` и caches, входят в общий budget; swap и core dumps выключены. Реальное поведение swap и accounting должно быть доказано на целевом Linux-host. | **Высокий:** заполнение tmpfs или миллионов пустых файлов даёт OOM/DoS; swap/dump оставляет source на диске. `noexec` не мешает Python читать и интерпретировать файл, поэтому это не граница исполнения. |
| **CPU cap** | Kernel-enforced aggregate CPU quota на всю job cgroup, а не soft shares/priority; значение профиля ниже. Все этапы и дочерние процессы используют общий budget. | **Высокий:** бесконечный цикл/несколько subprocess занимают весь хост при мягком либо per-PID лимите. CPU quota без wall-clock всё ещё допускает вечный job. |
| **Memory cap** | Hard cgroup limit с учётом tmpfs и descendants; swap отключён, OOM завершает весь job, лимит не увеличивается при retry. Рабочий supervisor имеет отдельный ограниченный budget и резерв памяти. | **Высокий:** большие аллокации и tmpfs обходят неполное accounting, убивают host/worker и чужие jobs. Софт-лимит не является верхней границей. |
| **PID cap** | Cgroup PID/task cap включает потоки и всех descendants; нельзя создавать новые unmanaged cgroups/namespaces. Дочерний процесс не может сменой process group уйти из accounting. | **Высокий:** fork/thread bomb истощает PID и память. Ограничение только основного Python процесса либо числа subprocess в API не покрывает threads/внуков. |
| **Wall-clock cap** | Независимый от guest и worker task watchdog отсчитывает monotonic deadline с allocation sandbox, включает compile/public/hidden/static stages; deadline не сбрасывается между этапами. Cleanup имеет отдельный короткий budget. HTTP timeout не является stop для job. | **Высокий:** sleep/deadlock или дочерний процесс живёт после HTTP disconnect. Закрытие запроса или timeout тестовой функции не гарантирует остановку среды. |
| **Disk cap** | Writable storage только tmpfs с aggregate byte/inode caps; artifact export/архивы не поддерживаются в раннем Python профиле. Runtime logs/spool/image cache вне guest имеют отдельные bounded budgets и не сохраняют source. | **Высокий:** множество пустых файлов, большие файлы или runtime spool заполняют host даже при ограниченной памяти guest. Host/shared cache также создаёт cross-tenant остатки. |
| **Output cap** | Бounded streaming capture до лимита, не post-hoc slice после накопления. Суммировать stdout/stderr всех этапов и descendants; превышение останавливает job как output/resource violation, retained prefix bounded с `truncated`. Raw output не используется как test report и не пишется в логи. | **Высокий:** output flood забивает RAM capture, transport, БД и LLM. Backpressure не должен оставлять job бесконечно ждать чтения. |
| **Allowlist images** | Только серверный каталог digest-pinned образов с provenance, проверкой зависимостей и отзывом. Неизвестный digest отклоняется до allocation; runtime pull/install по данным клиента запрещён. | **Критический:** произвольный/подменённый image содержит privileged helper/backdoor; mutable tag даёт незаметную supply-chain подмену. |
| **Allowlist commands** | Серверный fixed argv-профиль Python/compile/test/static stages, без shell, произвольного executable, env, cwd, аргументов/путей клиента. Запрет local config/plugin discovery из source; разрешены только server-owned plugins, не пользовательский `conftest.py`. | **Критический:** shell injection/path подменяют pipeline. **Высокий:** импорт пользовательского plugin/config исполняет его ещё на test discovery. Allowlist argv не ограничивает действия самого Python-кода внутри guest. |
| **Allowlist tests** | Immutable server-owned exercise version, test-bundle digest, mode и rubric. Клиент не передаёт source/path/expected/count tests; IDs не преобразуются в filesystem paths. Hidden evaluator отделён от student interpreter, отчёт guest не считается истинным pass. | **Высокий:** подмена тестов/monkeypatch harness/печать fake report даёт ложный pass. Read-only hidden source внутри среды всё ещё читается и может быть выведен. |
| **Cleanup после timeout** | Внешний supervisor останавливает sandbox и весь cgroup, включая детей с новой process group; подтверждает нулевые tasks и удаление среды/tmpfs/capture/IPC. Идемпотентная повторная уборка; без подтверждения — quarantine. | **Высокий:** kill одного PID оставляет grandchildren с нагрузкой и доступом к job data. Возврат `timeout` сам по себе не означает уборку. |
| **Cleanup после cancel** | Ownership/авторизация перед cancel; durable переход и generation fencing не позволяют принять поздний success. Завершение cancel требует той же подтверждённой остановки; гонка result/cancel решается атомарно. | **Высокий:** IDOR отменяет чужой job; late response создаёт evidence после отмены или меняет terminal state. |
| **Cleanup после worker crash** | Durable launch intent/job registry, lease/heartbeat и независимый supervisor/reaper; reconciliation при восстановлении по server-owned resource IDs. Без worker должен действовать guest lifetime deadline; при недоступном runtime host изолируется и не получает новые jobs. | **Высокий:** crash до записи ID оставляет orphan; TTL только в упавшем worker бесполезен. «Exactly once» без recovery/fencing скрывает двойной запуск. |
| **mTLS / equivalent** | Выбран mTLS с проверкой CA, срока, server hostname/SAN и workload identity обеих сторон. Credentials доступны только trusted orchestration, не guest. Static `RUNNER_AUTH_TOKEN` поверх private сети сам по себе не принят как эквивалент. Альтернатива требует отдельного review identity, audience/scope, expiry и replay protection. | **Критический:** MITM/неавторизованный worker получает source или присылает fake pass; украденный bearer даёт доступ до отзыва. mTLS подтверждает identity, но не честность скомпрометированного worker. |
| **Private network** | Endpoint не публикуется в Интернет; ingress только от identity/API, management/runtime отдельно, egress worker только к необходимому runner control plane. Нет доступа к основной БД/AI Gateway/metadata; `RUNNER_URL` только из доверенной config, без redirect/proxy из client input. | **Критический:** открытый endpoint позволяет чужие jobs/DoS; worker с широким доступом становится мостом к production после escape. Private IP не заменяет mTLS. |
| **Credential rotation** | Предложенный TTL сертификата ≤24 ч, ротация каждые 6 ч, overlap ≤1 ч; compromised identity отзывается немедленно с закрытием старых сессий. Нет ключей в image/job/env guest/logs. При expiry/revocation/невозможности обновить credential — отказ, не insecure fallback. | **Критический:** долгоживущий ключ из dump/log позволяет impersonation и раскрытие jobs. Ротация без отзыва старых credentials сохраняет путь атаки. |
| **Unavailable / fail-closed** | Missing config/unverified worker/auth failure/transport timeout/5xx/overload/invalid schema/unknown outcome ⇒ публичный `unavailable`. Никаких local execution, fake pass, AI-derived test success или objective success evidence. Retry только bounded, тот же key, без повторного allocation при неизвестном исходе. | **Критический:** fallback в API обходит sandbox и exposes production. **Высокий:** fake success и retry storm отравляют mastery и истощают очередь. |

## Предлагаемый численный профиль: `python-authored-v1`

Это **design proposal для коротких authored Python-упражнений**, не проверенная
production config и не инструкция включения. Значения выбираются сервером,
фиксируются версией policy и не расширяются клиентом/LLM. Если упражнение не
помещается в профиль, оно остаётся недоступным либо проходит отдельное review.

| Budget | Предложение и отказ |
|---|---|
| CPU | 1 vCPU aggregate quota, 100 ms accounting period. CPU quota ограничивает скорость, не общее время — дополнительно обязателен wall-clock cap. |
| Memory | 512 MiB hard на весь job, включая tmpfs; swap 0. OOM ⇒ остановка всего job и resource violation. |
| PID / FD | 32 tasks, включая threads; 64 open descriptors на процесс плюс ограниченное число tasks. PID exhaustion ⇒ resource violation, не автоматическое увеличение cap. |
| Wall-clock | 15 с с allocation до конца всех guest stages; cleanup ≤5 с. Deadline/cleanup failure ⇒ остановка/quarantine, не новый 15-секундный запуск каждого этапа. |
| Disk | 16 MiB совокупно для всех writable tmpfs, 4096 inode совокупно; shared memory включена в этот же budget. Нет writable layer/core dumps. |
| Output | 64 KiB stdout+stderr совокупно на job, включая test/analyzer output; превышение ⇒ output/resource violation. Hidden raw output наружу не отдаётся. |
| Transport | Source ≤64 KiB UTF-8; decoded request body ≤128 KiB, result body ≤128 KiB, ≤100 structured findings, ≤256 public/hidden tests суммарно. Лимит проверяется до buffering/декомпрессии/JSON parsing; неожиданные compressed payload отклоняются. |
| Queue / abuse | 6 submissions/мин на пользователя, burst 2; ≤1 active +2 queued на пользователя, ≤64 jobs в общей очереди, queue TTL 60 с. Исчерпание ⇒ контролируемый отказ без allocation. |
| Host capacity | Начально ≤1 active job на execution-host; число hosts и global budget фиксирует оператор. Admission учитывает память trusted supervisor/OS и резерв для cleanup; превышение capacity ⇒ unavailable. |

Если runtime/kernel не может доказуемо применить хоть один cap, admission
отклоняется до выполнения. Политика ограничивает также compile/static analyzers,
которые обрабатывают hostile source: они не должны работать в процессе API или
trusted evaluator с секретами. Оператор должен отдельно доказать на целевом host,
что runtime применяет hard limits, а не только soft reservations, и что accounting
включает descendants.

## Дополнительные границы, обязательные для разделов 36–41

### Host mounts, secrets и runtime control plane

Запрещены host filesystem mounts, Docker/container runtime socket, host PID/IPC/network,
production environment variables, cloud metadata access, SSH keys, API/AI/database
credentials и общие volumes. Даже если код не может прочитать файл напрямую, его наличие
в окружении создаёт цель для `/proc`, ошибочного helper-а или будущей уязвимости runtime.

Worker host должен быть отдельным execution-host с минимальным доступом к control plane.
Компрометация одного sandbox должна вести максимум к потере этого job/host, а не к
production secrets. Secrets не должны попадать в job request, image layers, stdout,
stderr, exception text, metrics labels, traces или normalized result.

### Логи и данные для Tutor Engine/LLM

`stdout`, `stderr`, source, filenames, exception messages и static findings считаются
недоверенным контентом. Их нужно ограничивать по размеру, редактировать очевидные
credentials/PII и хранить только с минимальным retention. В логи нельзя писать source,
токены, cookies, connection strings, полные env или лишние персональные данные.

В разделе 40 код, task, test results и linter output передаются LLM. Комментарий,
строка вывода или имя файла может содержать prompt injection, например попытку
убедить Tutor Engine раскрыть system prompt, вызвать инструмент или изменить оценку.
Такой текст должен поступать как цитируемые данные с жёстким разделением инструкций;
LLM не является источником policy и не может выбирать image, command, test, secret или
итоговый pass. Объективный normalized result строится до LLM, а feedback не меняет
security state и evidence без серверной валидации.

### AST/static analysis

AST-фильтр, denylist импортов, ruff или mypy **не являются границей безопасности**.
Python позволяет выражать опасные действия через динамические импорты, reflection,
объекты, subprocess/OS APIs, native extensions и resource exhaustion; фильтр также
можно обойти изменением формы кода или использовать bug в самом анализаторе.
Статический анализ может быть дополнительным finding, но никогда не заменяет
network isolation, privilege separation, resource limits и уничтожение sandbox.
Нельзя добавлять режим «если AST чистый, разрешить исполнение в API».

### Hidden tests, integrity и idempotency

API должен создавать server-side job с непредсказуемым idempotency key и сохранять
связь с пользователем, `CodingAttempt`, exercise version и policy digest. Worker
принимает только допустимый job, а API принимает результат только от
аутентифицированного worker и только один раз. Поздние, дублирующие или
противоречащие ответы не должны перезаписывать terminal state.

Если worker не может доказать, что применил именно зафиксированные image, commands,
public/hidden tests и policy limits, результат считается недействительным. Нельзя
выдавать hidden test source; наружу возвращаются только нормализованные bounded
счётчики и безопасные findings.

### Будущие языки и browser preview

Разделы 37–39 не расширяют текущий scope и не являются основанием включать новые
исполнители. JavaScript/TypeScript требуют отдельной package allowlist и запрета
произвольного install; C++ требует отдельного решения для compiler/native-code
рисков; React/HTML preview требует изолированного origin и iframe-политики без
доступа к cookies основной сессии. Эти границы нельзя считать покрытыми Python
runner design.

## Критерии допуска worker

До смены текущего fail-closed поведения должны быть доказаны, а не предположены:

1. API никогда не исполняет пользовательский код и не монтирует runtime socket.
2. Каждый job получает отдельный sandbox, непривилегированный UID, read-only base,
   ограниченный tmpfs и отсутствие host mounts/secrets/network.
3. CPU, memory, PID, wall-clock, disk и output caps — hard, численные,
   versioned и применяются ко всему process tree.
4. Только digest-pinned allowlist image, серверные commands и серверные public/hidden
   tests; клиент не управляет ни одним из них.
5. Timeout, cancel и worker crash приводят к подтверждённому cleanup либо к
   quarantine/`indeterminate`; orphaned resources не считаются убранными.
6. API↔worker защищены private network и mTLS/equivalent с rotation, expiry,
   replay protection и безопасным отказом.
7. Невалидный или отсутствующий worker result не даёт pass, mastery credit или
   evidence.
8. Логи, traces, metrics и ответы API не содержат source, secrets и лишние PII;
   output bounded и prompt-injection-safe для Tutor Engine.
9. Проверены adversarial cases: infinite loop, fork/thread bomb, memory/disk fill,
   output flood, subprocess, dynamic import, archive/path traversal, duplicate/late
   result, cancel race, worker crash и expired credentials.

## Что реально проверено в рамках этой задачи

- Прочитан Prompt 07 и разделы 35–41 спецификации.
- Прочитаны локальные инструкции `task-router`, `security-review` и
  `verification-strategy`.
- Выполнен только письменный анализ; код не запускался и worker не разворачивался.
- Implementation code не изменялся.

## Непроверенное и ограничения

- Реальная изоляция контейнера/VM, seccomp/AppArmor/gVisor, network namespace,
  cgroups, PID limits, tmpfs quotas и cleanup на Linux-host не проверены.
- Реальные mTLS, private routing, rotation/revocation и worker crash recovery не
  проверены.
- В исходном Prompt 07 численные лимиты CPU/memory/PID/time/disk/output не
  заданы; приведённый выше профиль — только предложение для отдельного review,
  поэтому его пригодность к production не подтверждена.
- Не проверены PostgreSQL, очередь, браузерный end-to-end flow и фактическое
  поведение Tutor Engine/LLM с hostile output.
- Настоящая гарантия отсутствия секретов в deployment environment и image supply
  chain не проверена.

До этих проверок единственное принятое безопасное поведение — `unavailable`
без локального fallback и без evidence за неисполненный или недоказанный запуск.
