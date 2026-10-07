# Черновики и учебные занятия

Весь API требует аккаунта и завершённого onboarding. Изменяющие запросы требуют CSRF. Все GET/POST дополнительно требуют `X-Account-Scope` из текущего `/me`: это непрозрачное условие совпадения аккаунта, не credential или выбор владельца. Старая вкладка после переключения общих cookies получает 409 `account_changed` до чтения или записи приватной работы. Ответы, включая ошибки валидации, имеют `Cache-Control: no-store`. Владелец берётся из сессии; клиент не передаёт owner, оценку, правильность или completion.

## Черновики

| Метод | Путь | Результат |
|---|---|---|
| GET | `/learning/drafts?kind=...&resource_id=...&version=...&milestone_id=...` | Текущий owned черновик без бизнес-записей |
| POST | `/learning/drafts` | Сохранение или очистка по ожидаемой revision |

POST имеет форму `{identity, expected_revision, content}`. Identity содержит `kind`, `resource_id`, `version`, `milestone_id`.

| kind | resource_id | version / milestone_id | content |
|---|---|---|---|
| lesson_flow | Public lesson ID | Положительный public version / пустой этап | `{step: 1..3, answers: {question_id: selected_choice}}` |
| coding | Public authored function exercise ID | Положительный public version / пустой этап | `{source_code, backup_source: string|null}`, до 20 000 символов каждый |
| reflection | Public lesson ID | Положительный public version / пустой этап | `{text}`, до 10 000 символов |
| project_milestone | Owned project UUID | `0` / этап immutable template | `{artifact_text, repository_url}`, до 25 000 / 2048 символов |

Ответ: `{identity, revision, content, updated_at}`. Отсутствующая запись имеет revision 0 и null content/date. `content: null` очищает запись, сохраняя новую revision. Неизвестные поля запрещены. Варианты ответа должны принадлежать точной версии текущего pending knowledge check; черновик не является его результатом.

Одновременно изменённая revision возвращает 409 с кодом `draft_conflict`. Клиент отдельно читает текущий вариант и сохраняет текст в редакторе, пока пользователь не выберет вариант. Ошибка сети не разрешает перезапись. Перед явной заменой сохраняется локальный backup. До 500 identity на аккаунт: новые записи сверх лимита отклоняются, существующие не вытесняются. Локальный cache очищается при logout; серверная запись остаётся приватной в аккаунте.

## Таймер

| Метод | Путь | Результат |
|---|---|---|
| GET | `/learning/study-session` | `{session: current|null}` |
| GET | `/learning/study-sessions?limit=20` | Последние записи, limit 1..50 |
| POST | `/learning/study-sessions/start` | Запуск или возврат существующего открытого таймера; body `{}` |
| POST | `/learning/study-sessions/{id}/{action}` | Переход с body `{expected_revision}` |

Actions: `heartbeat`, `pause`, `resume`, `finish`, `abandon`. Статусы: `active`, `paused`, `completed`, `abandoned`. Завершённый/отменённый таймер не возобновляется. Один аккаунт имеет максимум один active/paused таймер; повторный start не создаёт второй и не возобновляет истёкший.

Сервер фиксирует focus и оценки времени из read-only плана на момент начала. Client heartbeat каждые 20 секунд подтверждает открытый отсчёт. Сервер ограничивает интервал 60 секундами и всё занятие 8 часами. GET истёкшего таймера показывает paused без записи; продолжение требует resume. При смене вкладки UI отправляет pause; при потере связи действует серверный предел. Время не подтверждает внимание или выполнение плана и не создаёт evidence/mastery.

## Миграции и запуск

Новая линейная цепочка: `0037_lesson_reflections` → `0038_study_drafts` → `0039_study_sessions`. Upgrade добавляет таблицы и ограничения, не переписывает аккаунты, immutable versions или учебные результаты. Downgrade 0039 удаляет только записи таймера; downgrade 0038 удаляет также серверные черновики. Существующие до этих ревизий данные сохраняются. Новые черновики и история не могут сохраниться в схеме без соответствующих таблиц.

Для Windows без Docker используйте актуальные launcher-ы `scripts/start-api.ps1` и `scripts/start-web.ps1`; API launcher применяет миграции. Для ручного запуска из `apps/api` используйте Python виртуального окружения: `.\.venv\Scripts\python.exe -m alembic upgrade head`.
