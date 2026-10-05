# PostgreSQL backup и restore drill

Этот runbook описывает только логический backup PostgreSQL для текущего
modular-monolith. S3, Kubernetes, SaaS-backup и enterprise DR сюда не входят.

## Что именно сохраняется

`backup.sh` — общий движок для Linux и Windows (`backup.ps1` извлекает из него
тот же Python-код). Он:

1. подключается к PostgreSQL по явным `PGHOST`, `PGPORT`, `PGUSER` и имени базы;
2. делает согласованный `pg_dump -Fc` через экспортированный snapshot;
3. проверяет, что `pg_dump` и `pg_restore` той же major-версии, что и сервер;
4. выполняет `pg_restore -l` до публикации backup;
5. пишет bundle `backups/<UTC-timestamp>-<id>/`:
   `database.dump`, `manifest.json` и маркер `SUCCESS`;
6. сохраняет в manifest SHA-256 файла, ревизии Alembic, количество строк и
   SHA-256 содержимого всех пользовательских таблиц, снимок всех колонок из
   `information_schema`;
7. применяет retention: 7 разных дней, 4 разных ISO-недели и 6 разных
   месяцев. Retention удаляет только полные bundles этого скрипта и этой базы.

Inventory не содержит фиксированного allowlist: он включает новые таблицы,
в том числе `rate_limit_state`, и nullable-поля `ai_usage_ledger`.
При drill сравниваются количества строк, SHA-256 канонического содержимого,
полный снимок колонок и `alembic_version`. Так проверяются значения (включая
`NULL` и JSON), а не только наличие колонок. В manifest и отчёте нет исходных
строк пользователей. Формат manifest — `mentor-pg-backup-v2`; старый v1
намеренно не объявляется value-verified. Каталог backup привязывается к
SHA-256 endpoint/database marker `.source`; другой сервер с базой того же имени
не сможет этим запуском участвовать в retention того же root.
Digest требует полного чтения и сортировки таблиц: предусмотрите свободное
место для PostgreSQL temporary files и окно без schema migrations. Это
логический backup, не PITR: рекомендованный RPO — до 24 часов при ежедневном
расписании; RTO измеряется drill, а не обещается заранее.

Это **не** копия `$PGDATA` и не backup Docker volume. Не останавливайте
PostgreSQL и не копируйте каталог данных «на лету»: для этого проекта
используется согласованный логический dump. Произвольное копирование работающего
PGDATA/volume может смешать страницы разных моментов времени и не сохранить
необходимый WAL; наличие файлов не доказывает восстанавливаемость. Для physical
backup нужен отдельный PostgreSQL-supported протокол и проверка, здесь его нет.

## Секреты и хранение

- `.env`, пароли, `PGPASSFILE` и ключи AI не должны попадать в Git, backup
  bundle, отчёты или аргументы команд.
- Дамп содержит пользовательские данные. Храните каталог backup вне checkout,
  с ACL только для backup-оператора и системного администратора.
- На Linux каталог должен принадлежать оператору и иметь mode `0700`.
  На Windows скрипт заменяет ACL каталога и оставляет Full Control только
  текущему пользователю и `SYSTEM`. При drill ACL каждого файла bundle
  сбрасывается к наследованию защищённого родителя, включая скопированные
  файлы с собственными permissive ACL.
- Скрипт требует `BACKUP_ENCRYPTED_STORAGE=1` как явное подтверждение, что
  каталог лежит на зашифрованном диске/томе (например, BitLocker или LUKS).
  Сам `pg_dump -Fc` не шифруется. Без этого подтверждения операция
  останавливается; скрипт **не проверяет** состояние BitLocker/LUKS. Проверка
  реального шифрования и безопасное отдельное хранение recovery key — задача
  оператора. Не выставляйте флаг на незашифрованном томе с реальными данными.
- Для паролей используйте файл `.pgpass`/`pgpass.conf` вне репозитория, с
  правами `0600` на Linux и ACL только для владельца на Windows. В примерах
  ниже путь к нему задаётся через `PGPASSFILE`; пароль не вставляйте в
  command line или task definition.
- `PGSERVICE` и `PGSERVICEFILE` намеренно запрещены: это предотвращает
  незаметное подключение к другой базе. Явно проверьте host, port, user и
  database перед запуском.
- Dump не сохраняет cluster-wide роли, пароль роли, конфигурацию PostgreSQL,
  `.env` или ключи Gateway. Их восстанавливают отдельно из защищённого
  источника; drill сознательно переносит ownership на тестовую роль и не
  восстанавливает production grants. Не восстанавливайте чужой/недоверенный
  dump: в архиве могут быть исполняемые SQL-функции.
- Каталог на том же диске, что PGDATA, не защищает от отказа диска. Выделите
  второй зашифрованный носитель и храните копию вне этого хоста (например,
  отключённый зашифрованный диск). Автоматической внешней репликации тут нет.

## Переменные окружения

Минимальный набор для backup:

```text
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=mentor
PGDATABASE=mentor
PGPASSFILE=<секретный файл вне репозитория>
BACKUP_ENCRYPTED_STORAGE=1
```

`BACKUP_REPO_ROOT` скрипт выставляет сам. `PGPASSWORD` допустим только как
секрет исходного подключения текущего процесса; дочерние клиенты его не
получают, поэтому для полного backup/drill нужен `PGPASSFILE`. Не используйте
`DATABASE_URL` в командной строке backup: скрипт принимает имя базы, а не URI.
Используйте отдельный backup root для каждого endpoint/database; `.source`
привязывает root при первом запуске. Если каталог уже заполнен без marker,
скрипт откажется его автоматически присваивать: заведите новый пустой root.
Не удаляйте marker ради обхода проверки. При миграции хоста старые backup
сохраняют в отдельном защищённом каталоге для drill, новый root создают заново.

## Linux: ручной запуск и расписание

Проверить клиентские версии и создать отдельный защищённый каталог:

```bash
command -v pg_dump pg_restore
pg_dump --version
pg_restore --version
install -d -m 700 /var/backups/mentor-postgres
```

Один backup:

```bash
cd /srv/ai_programming_bot_project
set -a
. /etc/mentor/backup.env
set +a
bash ./scripts/backup.sh \
  --database "$PGDATABASE" \
  --backup-dir /var/backups/mentor-postgres \
  --daily 7 --weekly 4 --monthly 6
```

Для production лучше запускать от отдельного системного пользователя с
доступом только к PostgreSQL и каталогу backup. Пример cron (02:15 UTC):

```cron
CRON_TZ=UTC
15 2 * * * cd /srv/ai_programming_bot_project && set -a && . /etc/mentor/backup.env && set +a && bash ./scripts/backup.sh --database "$PGDATABASE" --backup-dir /var/backups/mentor-postgres --daily 7 --weekly 4 --monthly 6 >> /var/log/mentor-backup.log 2>&1
```

Вместо cron можно использовать systemd timer с тем же `backup.env`; важно
запускать только одну копию. Встроенный lock `.backup.lock` завершает второй
параллельный запуск без удаления существующих backup.
`/etc/mentor/backup.env` — отдельный root/operator-owned shell-файл `0600`
с безопасными assignments, не исходный project `.env`; cron его исполняет.
Задайте абсолютный `PYTHON=/srv/mentor-venv/bin/python` (Python 3.12+,
зависимости `apps/api/requirements.txt`) и `PG_BIN=/usr/lib/postgresql/17/bin`.
Не полагайтесь на PATH интерактивного терминала. Защитите и ротируйте log.
`CRON_TZ` зависит от реализации cron: проверьте timezone установленного daemon
или используйте systemd timer с `OnCalendar=*-*-* 02:15:00 UTC`.

Для больших таблиц администратор PostgreSQL должен задать на backup-role
ограничения сортировки, например `ALTER ROLE mentor_backup SET work_mem =
'16MB'` и `ALTER ROLE mentor_backup SET temp_file_limit = '1GB'` (конкретный
бюджет сверить с объёмом БД). Скрипт использует statement timeout 5 минут,
lock timeout 30 секунд и `--timeout` для внешних команд, но это **не** общий
deadline всей операции. Для systemd задайте `TimeoutStartSec=1h`; для Windows
добавьте `-ExecutionTimeLimit (New-TimeSpan -Hours 1)` к task settings.
После принудительного завершения проверяйте `.partial`, lock и временные базы.
Нагрузка full-scan/sort и capacity на production объёме здесь не проверены.

## Windows/dev: ручной запуск и Scheduled Task

PowerShell запускает тот же движок и не требует WSL:

```powershell
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "5432"
$env:PGUSER = "mentor"
$env:PGDATABASE = "mentor"
$env:PGPASSFILE = "C:\Users\<user>\.pgpass-mentor"
$env:BACKUP_ENCRYPTED_STORAGE = "1"
$env:PG_BIN = "C:\Program Files\PostgreSQL\17\bin"
$env:PYTHON = "C:\ai_programming_bot_project\.venv\Scripts\python.exe"

.\scripts\backup.ps1 -Mode backup `
  --database mentor `
  --backup-dir D:\ProtectedBackups\mentor-postgres `
  --daily 7 --weekly 4 --monthly 6
```

Для Scheduled Task создайте локальный wrapper вне репозитория, который задаёт
эти переменные окружения и вызывает `backup.ps1`; не храните пароль в
`-Argument` или XML задачи. Запускайте задачу от отдельной Windows-учётной
записи с правами на зашифрованный каталог. Пример регистрации (без секрета):

```powershell
$action = New-ScheduledTaskAction `
  -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -Argument "-NoProfile -NonInteractive -File C:\Ops\mentor-backup-wrapper.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2:15am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -MultipleInstances IgnoreNew
# Dev: запуск при входе текущего пользователя, без пароля в task definition.
$principal = New-ScheduledTaskPrincipal `
  -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
  -LogonType Interactive
Register-ScheduledTask -TaskName "Mentor PostgreSQL backup" `
  -Action $action -Trigger $trigger -Settings $settings -Principal $principal
```

Локальная разработка может запускать backup вручную. Не направляйте dev
backup в каталог репозитория: default `backups/` игнорируется Git, но
защищённый отдельный диск предпочтительнее.
Dev-задача с `Interactive` выполняется только при logged-on пользователе.
Для unattended server настройте отдельную учётную запись через Task Scheduler
UI (не сохраняйте её пароль в скрипте) и проверьте реальный запуск вне
интерактивного терминала. Пример регистрации выше расписание сам не включает,
пока оператор его не выполнит.

## Restore drill

Drill **не перезаписывает** исходную базу. Он:

1. проверяет `SUCCESS`, manifest и SHA-256;
2. снова запускает `pg_restore -l`;
3. требует PostgreSQL той же major-версии;
4. создаёт новое имя `mentor_restore_<timestamp>_<id>` и никогда не использует
   `DROP DATABASE`, `IF EXISTS` или существующую целевую базу;
5. восстанавливает через `pg_restore --exit-on-error --single-transaction
   --no-owner --no-privileges`;
6. сравнивает counts, SHA-256 строк, колонки и Alembic revision;
7. при `--smoke` поднимает отдельный API только на `127.0.0.1`, проверяет
   `/health` и пытается проверить `/ready`;
8. оставляет временную базу и агрегированный drill-report для осмотра.

Для drill используйте отдельный PostgreSQL instance/host без production
секретов; перенесите туда bundle и подтвердите encrypted storage.
Не оставляйте `PGHOST` от production backup по привычке.
Login `PGUSER` для restore должен быть отдельной ролью, не владельцем
production БД: без SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS и без
членства в привилегированных ролях. Он подключается к `postgres` и владеет
только временной БД. Отдельный `DRILL_ADMIN_USER` создаёт базу с этим owner;
ему нужны CREATEDB и право назначить эту роль владельцем (или superuser
**только на изолированном drill instance**). Административный пароль передаётся только через
`DRILL_ADMIN_PASSFILE` (или `PGPASSFILE`), не через argv.
Перед drill удалите `PGPASSWORD` из окружения (`unset PGPASSWORD` на Linux,
`Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue` в PowerShell):
подключения используют защищённые passfiles, не унаследованный пароль.

Linux:

```bash
set -a; . /etc/mentor/drill.env; set +a
# drill.env: отдельные PGHOST/PGPORT/PGUSER/PGPASSFILE, PYTHON, PG_BIN,
# BACKUP_ENCRYPTED_STORAGE=1, не production credentials.
export DRILL_ADMIN_USER=mentor_drill_admin
export DRILL_ADMIN_PASSFILE=/etc/mentor/pgpass-admin
bash ./scripts/restore-drill.sh \
  --bundle /var/backups/mentor-postgres/<UTC-timestamp>-<id> \
  --database mentor \
  --backup-dir /var/backups/mentor-postgres \
  --api-dir /srv/ai_programming_bot_project/apps/api \
  --smoke
```

PowerShell:

```powershell
# Предварительно переключите PGHOST/PGPORT/PGUSER/PGPASSFILE на drill instance.
$env:DRILL_ADMIN_USER = "mentor_drill_admin"
$env:DRILL_ADMIN_PASSFILE = "C:\Ops\pgpass-admin"
.\scripts\restore-drill.ps1 `
  --bundle D:\ProtectedBackups\mentor-postgres\<UTC-timestamp>-<id> `
  --database mentor `
  --backup-dir D:\ProtectedBackups\mentor-postgres `
  --api-dir C:\ai_programming_bot_project\apps\api `
  --smoke
```

Скрипт печатает только имя временной базы, revision, агрегированные проверки и
путь к report. URL, пароль, ключи, SQL-ошибки и строки таблиц не печатаются.
После проверки удалите временную базу вручную, только убедившись, что это имя
начинается с `mentor_restore_` и принадлежит drill:

```sql
-- Подставить точное имя из отчёта и проверить current_database/current_user.
-- Выполнить административной ролью только на drill instance:
-- DROP DATABASE "mentor_restore_20261005_021500_example";
```

Если `pg_restore` или smoke падает, временная база намеренно остаётся для
расследования; это не означает, что исходная база была изменена. После
расследования удалите её тем же безопасным способом.

## `/health`, `/ready` и Alembic

`--smoke` требует, чтобы backup был на текущем code head. В restored базе drill
выполняет реальные:

```text
alembic current
alembic heads
```

и сравнивает их с `alembic_version` из manifest. `--allow-older-revision`
разрешает только осознанный drill старого backup без заявления, что схема
соответствует текущему коду.

Сейчас в API есть `/health`; `/ready` может отсутствовать и тогда в отчёте
будет `ready=not_implemented`. Для строгого production gate используйте
`--smoke --require-ready`: он должен завершиться ошибкой, пока `/ready` не
появится. Поэтому restore drill с `--require-ready` здесь честно считается
непрошедшим до отдельного изменения API, которое не входит в этот backup-only
scope.

## Чек-лист оператора

- [ ] PostgreSQL запущен, фактические host/port/user/database проверены.
- [ ] `pg_dump`/`pg_restore` той же major-версии, что сервер.
- [ ] backup-каталог вне checkout, ACL ограничен, storage зашифрован.
- [ ] `SUCCESS`, `pg_restore -l` и SHA-256 пройдены.
- [ ] Manifest содержит `SkillEvidence`, `ai_usage_ledger`,
      `rate_limit_state` (если таблица/колонка присутствует) и nullable-поля
      ledger через общий inventory.
- [ ] Restore создан в новой `mentor_restore_*` базе и не менял исходную.
- [ ] Сравнены counts, row digests, columns и `alembic current`/`heads`.
- [ ] `/health` прошёл; `/ready` прошёл или явно отмечен
      `not_implemented`.
- [ ] Временная база и report обработаны, секреты не попали в логи.

## Частота drill и отказ

Выполняйте drill ежемесячно и после смены версии PostgreSQL, backup-скрипта
или схемы, особенно добавления rate-limit/ledger state. Success backup-job
не равен success drill. Ошибка любой обязательной проверки даёт nonzero exit;
`.partial` и bundles без `SUCCESS` нельзя считать backup. Lock после аварии
не удаляется автоматически: проверьте, что процесс завершён, и удалите только
пустой `.backup.lock` внутри проверенного backup root.

Без новой alerting-системы оператор ежедневно проверяет exit code/Task
Scheduler `LastTaskResult`, свежесть `SUCCESS` (не старше 26 часов), свободное
место и последнюю дату прошедшего drill. При ошибке: сохранить последний
проверенный backup, не чистить вручную весь каталог, проверить доступность
БД, права, storage, место и версии клиентов; повторить backup, затем drill.
Низкоуровневый stderr намеренно не логируется (может содержать данные).
Для диагностики используйте локальный защищённый терминал, не включайте
`set -x`, PowerShell transcript или публикацию конфигурации.
Scheduler должен доставлять только безопасный статус существующим механизмом
оператору; в этом scope нет Slack/Telegram-интеграции. Расписание/доставка
ошибки не считаются проверенными без фактического scheduled запуска.

## Восстановление сервиса (не автоматизировано)

Drill не переключает production. При аварии остановите API/web writes,
сохраните неисправную БД/volume для расследования, восстановите проверенный
dump **в новую БД** на подготовленном защищённом instance, восстановите отдельно
секреты/roles/grants и примените подходящий code release. Проверьте counts,
row digests и `alembic current`/`heads`; для старого snapshot сначала проверьте
миграции на копии, не обновляйте единственный сохранившийся источник.
После `/health`/`/ready` и проверки пользователя с прогрессом переключите
server-only `DATABASE_URL` на новую БД, перезапустите API/web и наблюдайте.
Старую БД не удаляйте до подтверждения. Rollback — вернуть прежний URL, если
на новой базе ещё не было writes; после новых writes нужен план согласования
данных, а не слепой откат.

Не объявляйте backup рабочим только потому, что появился файл: доказательством
служит успешный restore drill.

## Реальные проверки 5 октября 2026 года

- Нативное исходное подключение: PostgreSQL 17.11, database `mentor`,
  SQLAlchemy dialect `postgresql`, driver `psycopg`, revision `0030`.
  Исходную БД не мигрировали, не дампировали и не изменяли.
- На отдельном loopback-кластере PostgreSQL 17.11 с синтетическими данными
  выполнены `upgrade head`, `downgrade 0030`, повторный `upgrade head`;
  counts четырёх sentinel-таблиц сохранились (`1,1,1,2`).
  `alembic check` **не прошёл**: модели не объявляют
  `ix_knowledge_chunks_skill_version`, созданный миграцией `0031`.
  Backend/миграции в этой задаче не изменялись.
- На той же disposable-копии PowerShell backup/restore и Git Bash backup
  успешно обработали 44 таблицы; restore сравнил counts, row digests,
  columns и revision. Данные были только синтетическими. Дополнительно
  проверены `rate_limit_state` с JSON и nullable ledger-колонка/строка;
  в исходной схеме отдельной `rate_limit_state` нет.
- Smoke восстановленной head-копии: `/health` прошёл; `/ready` — 404,
  отчёт `passed_with_ready_gap`. Строгий `--require-ready` вернул exit 1.
- Collision с существующей БД и неверный SHA-256 отклонены.
  Неверный checksum отклонён до `CREATE DATABASE`.
- Retention проверен на 250 синтетических bundles: union daily/weekly/monthly,
  incomplete/foreign/unrelated artifacts сохранены; duplicate manifest keys
  и небезопасные database names отклонены.
- Проверены source-root binding, redaction ошибочных аргументов с синтетическим
  credential-like значением, отказ restore-роли с `pg_execute_server_program`
  и reset permissive ACL скопированного dump-файла.
- `python -m pytest -q -p no:cacheprovider`: **186 passed, 3 skipped**
  (PostgreSQL-only gate не включался); `npm run lint` и `npm run build` —
  exit 0.

Тестовый кластер остановлен. Временные файлы с синтетическими данными остались
в системном `%TEMP%`: удаление было запрещено политикой среды. Реальные
пользовательские данные туда не копировались. Linux/prod, Docker/Compose, запуск cron
или Scheduled Task, реальное at-rest encryption, capacity/RTO на production
объёме, Runner isolation и browser E2E **не проверены**. Git Bash — не Linux
production verification. Эти скрипты не делают PITR и не автоматизируют
переключение сервиса на восстановленную БД.
