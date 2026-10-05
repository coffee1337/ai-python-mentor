---
name: verification-strategy
description: "Что и как проверять в этом проекте."
---

# verification-strategy

Проверяй минимальным содержательным набором под изменённую область, а не всем сразу. Отдельно фиксируй быстрый SQLite-контур и проверки, требующие настоящего PostgreSQL.

## Быстрый SQLite-контур

API: `cd apps/api && python -m pytest -q`. Текущая фикстура `client` явно создаёт SQLite `StaticPool` и подменяет `get_db`, поэтому этот прогон остаётся быстрым и проверяет API/доменное поведение, но не доказывает PostgreSQL semantics. SQLite migration-тесты с временными файлами и sentinel-данными также остаются быстрым контуром; они не заменяют проверку настоящей базы.

Добавляй тест, который падает до правки и проходит после; тест, зеркалящий реализацию, не считается проверкой. Доменные инварианты проверяй целевыми тестами: evidence ownership, assisted/independent, CSRF на изменяющих запросах, отсутствие ключей в ответе, валидация ответа AI схемой, rate limit, таймауты и fallback gateway.

## Локальный PostgreSQL

PostgreSQL 17 теперь установлен локально и должен быть запущен как служба. Перед отчётом о PostgreSQL-проверке обязательно докажи фактический dialect и базу через SQLAlchemy/SQL, а не по одной переменной окружения:

```powershell
cd apps/api
$env:DATABASE_URL = "<локальное значение DATABASE_URL; пароль не печатать>"
python -c "from sqlalchemy import create_engine,text; import os; e=create_engine(os.environ['DATABASE_URL']); c=e.connect(); print('dialect='+c.dialect.name); print('driver='+c.dialect.driver); print('database='+str(c.execute(text('select current_database()')).scalar_one())); print('server_version='+str(c.execute(text('show server_version')).scalar_one()))"
```

Обязателен Alembic round trip на этой же базе: сохранить sentinel/счётчики существующих данных, затем выполнить `python -m alembic upgrade head`, `python -m alembic check`, `python -m alembic downgrade 0001_initial`, `python -m alembic upgrade head` и снова подтвердить сохранность данных. Отчёт «round trip пройден» допустим только если все команды успешны и доказаны обе ревизии и данные; `alembic check` обязателен и ловит расхождение моделей с миграциями.

На 4 октября 2026 года PostgreSQL 17.11 локально имеет состояние службы `Running/Automatic`. Фактическое подключение подтверждено: `dialect=postgresql`, `driver=psycopg`, `database=mentor`. После исправления `0018_assessment_run_exercise_version` команды `upgrade head`, `alembic check`, `downgrade 0001_initial` и повторный `upgrade head` завершились с exit 0; Alembic round trip считается пройденным.

PostgreSQL-only проверки находятся в `apps/api/tests/test_postgres_specific.py` и намеренно не используют общую `client`-фикстуру SQLite. Gate требует одновременно явные `RUN_POSTGRES_TESTS=1` и `DATABASE_URL`; без `RUN_POSTGRES_TESTS=1` файл пропускается, а `DATABASE_URL` сам по себе не переключает обычный API-suite. Из `apps/api` запускай файл отдельно:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
$env:DATABASE_URL = "<локальное значение DATABASE_URL; пароль не печатать>"
python -m pytest -q -s tests/test_postgres_specific.py
```

Отдельный тест запускается тем же способом с node id, например:

```powershell
python -m pytest -q -s tests/test_postgres_specific.py::test_parallel_skill_evidence_updates_are_serialized
```

Фикстура печатает только доказательство фактических `dialect`, `driver` и `database` (например, `dialect=postgresql driver=psycopg database=mentor`); `DATABASE_URL` и пароль в вывод не попадают. На 4 октября 2026 года с `RUN_POSTGRES_TESTS=1` получено `3 passed`, а без gate — `3 skipped`.

## Остальные проверки

Фронтенд: `cd apps/web && npm run lint` (это `tsc --noEmit`) и `npm run build`. Линтер здесь — только типы; визуальные и поведенческие дефекты он не ловит.

Честно разделяй подтверждённое и непроверенное. Runner и его изоляция, end-to-end браузер и Docker/Compose остаются непроверенными; CI не запускался. Называй их непроверенными, а не «должно работать».

Не запускай повторно то, что уже зелёное без причины: каждый прогон стоит времени. При падении сначала отличи дефект продукта от дефекта теста и не меняй ожидаемое значение без основания.
