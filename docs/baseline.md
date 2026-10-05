# Baseline и текущая проверка worktree

## Статус exact baseline из prompt 00

Exact original baseline из `docs/prompts/00-bootstrap.md` недоступен: исторический stdout запуска 33 тестов не сохранён и восстановить его невозможно. В `docs/prompts/README.md` сохранено только подтверждение 33 тестов на SQLite, не полный вывод команд.

## Exact current worktree verification (не historical baseline)

Ниже — предоставленные результаты проверки **текущего изменённого worktree**, а не реконструкция stdout prompt00. Полные сырые логи не сохранены в этом документе:

- API, `cd apps/api && python -m pytest -q`: `75 passed, 39 warnings in 30.32s`.
- Web, `cd apps/web && npm.cmd run lint`: `tsc --noEmit`, exit 0.
- Web, `cd apps/web && npm.cmd run build`: Next.js compiled, `9/9` pages, exit 0.
- Alembic на временной SQLite: `upgrade head`, затем `alembic check` → `No new upgrade operations detected`.
- Миграционные тесты включают round trips с сохранением sentinel-данных, в том числе `0021_knowledge_check_sessions` → `0022_lesson_sessions` → downgrade до `0021` → повторный upgrade.
- `git diff --check`: clean.

Это не заменяет exact original baseline (33 tests), который остаётся недоступным. Реальный PostgreSQL и row locking, изоляция Runner, Compose и end-to-end браузер здесь не проверялись.
