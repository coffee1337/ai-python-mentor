"""Persist the authored content seen for each exercise version."""

import sqlalchemy as sa
from alembic import op


revision = "0017_exercise_content_snapshots"
down_revision = "0016_exercise_version_snapshots"
branch_labels = None
depends_on = None


_BACKUP_TABLE = "exercise_content_snapshot_downgrade"


def _versions_table():
    return sa.table(
        "exercise_versions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("exercise_id", sa.String(80)),
        sa.column("version", sa.Integer()),
        sa.column("content_snapshot", sa.JSON()),
    )


def _backup_table():
    return sa.table(
        _BACKUP_TABLE,
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
        sa.column("content_snapshot", sa.JSON()),
    )


def _stable_snapshots():
    # Keep this explicit and historical: later edits to authored modules must
    # not rewrite what a legacy v1 row means. Unknown ids remain nullable.
    return {
        "variables-v1": {
            "schema_version": 1,
            "exercise_id": "variables-v1",
            "version": 1,
            "lesson": {
                "id": "variables-v1",
                "title": "Переменные и присваивание",
                "skill_id": "python.variables",
                "minutes": 10,
                "body": "Переменная связывает имя со значением. В backend так хранят, например, число запросов. Присваивание вычисляет правую часть и связывает результат с именем слева. Повторное присваивание заменяет значение, а не создаёт математическое равенство.",
                "example": "requests = 2\nrequests = requests + 1\nprint(requests)  # 3",
                "question": "Что выведет код: count = 4; count = count + 2; print(count)?",
                "choices": ["4", "6", "2"],
                "answer": "6",
            },
            "checks": [
                {
                    "id": "variables-output-v1",
                    "prompt": "Что выведет count = 4; count = count + 2; print(count)?",
                    "choices": ["4", "6", "2"],
                    "answer": "6",
                    "explanation": "Сначала count равен 4, затем к нему прибавляется 2, поэтому результат — 6.",
                },
                {
                    "id": "variables-reassignment-v1",
                    "prompt": "Что делает присваивание x = x + 1?",
                    "choices": ["Увеличивает текущее значение x на 1", "Создаёт вторую переменную x", "Сравнивает x с 1"],
                    "answer": "Увеличивает текущее значение x на 1",
                    "explanation": "Правая часть вычисляется первой, а новое значение связывается с именем x.",
                },
            ],
            "assessment": {
                "id": "variables-v1",
                "skill_id": "python.variables",
                "difficulty": 0.15,
                "prompt": "Что выведет: count = 4; count = count + 2; print(count)?",
                "choices": ["4", "6", "2"],
                "answer": "6",
            },
            "hints": [
                {"level": 1, "kind": "direction", "text": "Проследи, какое значение получает имя после каждой строки присваивания."},
                {"level": 2, "kind": "concept", "text": "Повторное присваивание использует текущее значение имени и заменяет его новым результатом."},
                {"level": 3, "kind": "step", "text": "Сначала зафиксируй исходное значение count, затем вычисли правую часть второго присваивания и только потом определи вывод print."},
                {"level": 4, "kind": "pseudocode", "text": "прочитать исходное count\nприбавить 2 к текущему count\nвывести получившееся значение"},
                {"level": 5, "kind": "solution", "text": "После первого присваивания count равен 4. Второе присваивание вычисляет 4 + 2, поэтому print выводит 6."},
            ],
        },
        "conditions-v1": {
            "schema_version": 1,
            "exercise_id": "conditions-v1",
            "version": 1,
            "lesson": {
                "id": "conditions-v1",
                "title": "Условия",
                "skill_id": "python.conditionals",
                "minutes": 10,
                "body": "Условие if выбирает действие, когда выражение истинно. Ветка else выполняется иначе. В backend это помогает выбрать ответ в зависимости от входных данных. Оператор >= включает равенство; > не включает. Отступы определяют тело ветки.",
                "example": "age = 18\nif age >= 18:\n    print(\"adult\")\nelse:\n    print(\"minor\")",
                "question": "Что выведет пример при age = 18?",
                "choices": ["adult", "minor", "Обе строки"],
                "answer": "adult",
            },
            "checks": [
                {
                    "id": "conditions-boundary-v1",
                    "prompt": "Какая ветка выполнится при age = 18 и условии age >= 18?",
                    "choices": ["adult", "minor", "Обе"],
                    "answer": "adult",
                    "explanation": "Оператор >= включает граничное значение 18.",
                },
                {
                    "id": "conditions-else-v1",
                    "prompt": "Когда выполняется ветка else?",
                    "choices": ["Когда условие if ложно", "Всегда после if", "Только при синтаксической ошибке"],
                    "answer": "Когда условие if ложно",
                    "explanation": "else описывает альтернативную ветку для ложного условия.",
                },
            ],
            "assessment": {
                "id": "conditions-v1",
                "skill_id": "python.conditionals",
                "difficulty": 0.35,
                "prompt": "Какая ветка выполняется при age = 18 в условии age >= 18?",
                "choices": ["adult", "minor", "обе"],
                "answer": "adult",
            },
            "hints": [
                {"level": 1, "kind": "direction", "text": "Сравни значение age с порогом в условии и выбери ветку, которая выполняется при истинном сравнении."},
                {"level": 2, "kind": "concept", "text": "Оператор >= считает сравнение истинным и при равенстве левой и правой частей; else используется только при ложном сравнении."},
                {"level": 3, "kind": "step", "text": "Подставь значение age в сравнение, определи его истинность, затем выбери строку print внутри соответствующей ветки."},
                {"level": 4, "kind": "pseudocode", "text": "сравнить age с 18\nесли сравнение истинно — выбрать первую ветку\nиначе — выбрать ветку else"},
                {"level": 5, "kind": "solution", "text": "При age = 18 сравнение age >= 18 истинно, поэтому выполняется первая ветка и выводится adult."},
            ],
        },
    }


def _restore_downgrade_backup(connection):
    if _BACKUP_TABLE not in sa.inspect(connection).get_table_names():
        return
    versions = _versions_table()
    backup = _backup_table()
    for row in connection.execute(sa.select(backup)).mappings():
        connection.execute(
            versions.update()
            .where(versions.c.id == row["exercise_version_id"])
            .values(content_snapshot=row["content_snapshot"])
        )
    op.drop_table(_BACKUP_TABLE)


def upgrade():
    with op.batch_alter_table("exercise_versions") as batch_op:
        batch_op.add_column(sa.Column("content_snapshot", sa.JSON(), nullable=True))

    connection = op.get_bind()
    versions = _versions_table()
    for exercise_id, snapshot in _stable_snapshots().items():
        connection.execute(
            versions.update()
            .where(
                versions.c.exercise_id == exercise_id,
                versions.c.version == 1,
                versions.c.content_snapshot.is_(None),
            )
            .values(content_snapshot=snapshot)
        )
    _restore_downgrade_backup(connection)


def downgrade():
    op.create_table(
        _BACKUP_TABLE,
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content_snapshot", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("exercise_version_id"),
    )
    connection = op.get_bind()
    versions = _versions_table()
    backup = _backup_table()
    rows = connection.execute(
        sa.select(versions.c.id, versions.c.content_snapshot).where(
            versions.c.content_snapshot.is_not(None)
        )
    ).mappings()
    for row in rows:
        connection.execute(
            backup.insert().values(
                exercise_version_id=row["id"],
                content_snapshot=row["content_snapshot"],
            )
        )

    with op.batch_alter_table("exercise_versions") as batch_op:
        batch_op.drop_column("content_snapshot")
