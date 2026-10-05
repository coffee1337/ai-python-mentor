---
name: verification-strategy
description: "Что и как проверять в этом проекте."
---

# verification-strategy

Проверяй минимальным содержательным набором под изменённую область, а не всем сразу. Отдельно фиксируй быстрый SQLite-контур и проверки, требующие настоящего PostgreSQL.

## Быстрый SQLite-контур

API: `cd apps/api && python -m pytest -q`. Текущая фикстура `client` явно создаёт SQLite `StaticPool` и подменяет `get_db`, поэтому этот прогон остаётся быстрым и проверяет API/доменное поведение, но не доказывает PostgreSQL semantics. SQLite migration-тесты с временными файлами и sentinel-данными также остаются быстрым контуром; они не заменяют проверку настоящей базы.

Добавляй тест, который падает до правки и проходит после; тест, зеркалящий реализацию, не считается проверкой. Доменные инварианты проверяй целевыми тестами: evidence ownership, assisted/independent, CSRF на изменяющих запросах, отсутствие ключей в ответе, валидация ответа AI схемой, rate limit, таймауты и fallback gateway.

## PostgreSQL

Не предполагай наличие или состояние локальной службы по историческому отчёту. PostgreSQL-only тесты требуют явных `RUN_POSTGRES_TESTS=1` и `DATABASE_URL`; обычная client-фикстура остаётся SQLite. Проверяй только выделенную тестовую базу, не production.

Докажи фактический dialect/driver/database через SQLAlchemy и `SELECT current_database()`. Не печатай DATABASE_URL или пароль. Фикстура `tests/test_postgres_specific.py` уже выводит это доказательство и отказывается выдавать SQLite за PostgreSQL.

```sh
cd apps/api
RUN_POSTGRES_TESTS=1 python -m pytest -q -s tests/test_postgres_specific.py
alembic upgrade head
alembic check
```

CI использует PostgreSQL 17. Полный round trip до `0001_initial` проводится **только на пустой одноразовой базе** до создания sentinel: исторический downgrade удаляет прикладные таблицы и не может сохранять учебные данные.

Сохранность существующих данных проверяется отдельно: `scripts/migration-sentinel.py create`, downgrade только до baseline новой волны (`0031_knowledge_chunks`), повторный upgrade/check, затем `migration-sentinel.py verify`. Sentinel включает аккаунт и completion с точной immutable ExerciseVersion. Отдельный проход проверяет откат последней ревизии. Никогда не используй полный destructive downgrade как доказательство сохранности данных.

В отчёте различай локальный SQLite, фактически проверенный PostgreSQL в CI и непроверенный target host. Исторические результаты запусков не доказывают состояние текущей ревизии.

## Остальные проверки

Фронтенд: `cd apps/web && npm run lint` (это `tsc --noEmit`) и `npm run build`. Линтер здесь — только типы; визуальные и поведенческие дефекты он не ловит.

Честно разделяй подтверждённое и непроверенное. Проверки orchestration worker не доказывают фактическую изоляцию Runner host. End-to-end браузер и Docker/Compose называй проверенными только после их реального запуска. CI status читай для точного head SHA текущего PR.

Не запускай повторно то, что уже зелёное без причины: каждый прогон стоит времени. При падении сначала отличи дефект продукта от дефекта теста и не меняй ожидаемое значение без основания.
