"""Authorize exact assessment wrong-choice mappings for Mistake Memory."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from alembic import op


revision = "0025_assessment_mistake_mappings"
down_revision = "0024_authored_mistake_mappings"
branch_labels = None
depends_on = None


EXISTING_VERSION_IDS = {
    "mis-var-output-first-v1": UUID("d2494c05-49a7-474a-a149-000000000001"),
    "mis-var-output-partial-v1": UUID("d2494c05-49a7-474a-a149-000000000002"),
    "mis-cond-boundary-both-v1": UUID("d2494c05-49a7-474a-a149-000000000005"),
}


SEED_MAPPINGS = (
    {
        "exercise_id": "variables-v1",
        "question_id": "variables-v1",
        "wrong_choice": "4",
        "code": "mis-var-output-first-v1",
        "skill_id": "python.variables",
        "version_id": EXISTING_VERSION_IDS["mis-var-output-first-v1"],
    },
    {
        "exercise_id": "variables-v1",
        "question_id": "variables-v1",
        "wrong_choice": "2",
        "code": "mis-var-output-partial-v1",
        "skill_id": "python.variables",
        "version_id": EXISTING_VERSION_IDS["mis-var-output-partial-v1"],
    },
    {
        "exercise_id": "types-v1",
        "question_id": "types-v1",
        "wrong_choice": "string value",
        "code": "mis-types-string-v1",
        "skill_id": "python.variables",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000001"),
        "error_text": "Выбран вариант о строковом значении для числа 3.14.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, числовая запись с точкой "
            "смешивается со строковым значением."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Сравни запись числового значения "
            "с записью текста и назови тип значения до следующего шага."
        ),
        "remediation_exercise_id": "variables-v1",
    },
    {
        "exercise_id": "types-v1",
        "question_id": "types-v1",
        "wrong_choice": "None",
        "code": "mis-types-none-v1",
        "skill_id": "python.variables",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000002"),
        "error_text": "Выбран вариант об отсутствии значения после записи 3.14.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, присваивание числового "
            "литерала путается с отсутствием значения."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Проверь, какое значение связывается "
            "с именем после присваивания, не подставляя результат заранее."
        ),
        "remediation_exercise_id": "variables-v1",
    },
    {
        "exercise_id": "conditions-v1",
        "question_id": "conditions-v1",
        "wrong_choice": "minor",
        "code": "mis-cond-boundary-excluded-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000003"),
        "error_text": "Выбран вариант, исключающий граничное значение 18.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, оператор >= читается "
            "как строгое сравнение >."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Подставь граничное значение в >= "
            "и отдельно сравни его с поведением >."
        ),
        "remediation_exercise_id": "conditions-v1",
    },
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "conditions-v1",
        "question_id": "conditions-boundary-v1",
        "wrong_choice": "minor",
        "code": "mis-cond-boundary-excluded-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000003"),
    },
    {
        "exercise_id": "conditions-v1",
        "question_id": "conditions-v1",
        "wrong_choice": "обе",
        "code": "mis-cond-boundary-both-v1",
        "skill_id": "python.conditionals",
        "version_id": EXISTING_VERSION_IDS["mis-cond-boundary-both-v1"],
    },
    {
        "exercise_id": "boolean-v1",
        "question_id": "boolean-v1",
        "wrong_choice": "count = 0",
        "code": "mis-boolean-assignment-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000004"),
        "error_text": "Выбран вариант присваивания вместо проверки условия.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, присваивание и сравнение "
            "смешиваются при записи условия."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Сравни запись условия с присваиванием "
            "и проверь, что выражение должно вернуть."
        ),
        "remediation_exercise_id": "conditions-v1",
    },
    {
        "exercise_id": "boolean-v1",
        "question_id": "boolean-v1",
        "wrong_choice": "count < 0",
        "code": "mis-boolean-negative-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000005"),
        "error_text": "Выбран вариант, допускающий только отрицательные значения.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, направление сравнения "
            "с нулём читается наоборот."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Подставь ноль и положительное число "
            "и проверь, какое сравнение включает оба случая."
        ),
        "remediation_exercise_id": "conditions-v1",
    },
    {
        "exercise_id": "assignment-v1",
        "question_id": "assignment-v1",
        "wrong_choice": "5",
        "code": "mis-assignment-no-update-v1",
        "skill_id": "python.variables",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000006"),
        "error_text": "Выбран исходный результат после повторного присваивания.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, вторая строка не считается "
            "изменением значения x."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Запиши значение x после каждой строки "
            "и сравни его с первым присваиванием."
        ),
        "remediation_exercise_id": "variables-v1",
    },
    {
        "exercise_id": "assignment-v1",
        "question_id": "assignment-v1",
        "wrong_choice": "25",
        "code": "mis-assignment-square-v1",
        "skill_id": "python.variables",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000007"),
        "error_text": "Выбран результат, полученный как будто x умножается сам на себя.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, x * 2 читается как возведение "
            "текущего значения в квадрат."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Отдельно выпиши множитель и текущее "
            "значение x перед вычислением правой части."
        ),
        "remediation_exercise_id": "variables-v1",
    },
    {
        "exercise_id": "branch-v1",
        "question_id": "branch-v1",
        "wrong_choice": "Да",
        "code": "mis-branch-strict-boundary-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000008"),
        "error_text": "Выбран положительный ответ при сравнении score > 80 на границе 80.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, строгое > читается "
            "как сравнение, включающее равенство."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Сравни поведение > и >= на граничном "
            "значении, не меняя исходное условие."
        ),
        "remediation_exercise_id": "conditions-v1",
    },
    {
        "exercise_id": "branch-v1",
        "question_id": "branch-v1",
        "wrong_choice": "Зависит от типа",
        "code": "mis-branch-type-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000009"),
        "error_text": "Выбран ответ о типе вместо проверки заданного сравнения.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, вопрос о результате "
            "сравнения смешивается с вопросом о типе данных."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Сначала вычисли сравнение при score = 80, "
            "а затем проверь, нужна ли информация о типе."
        ),
        "remediation_exercise_id": "conditions-v1",
    },
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "conditions-v1",
        "question_id": "conditions-else-v1",
        "wrong_choice": "Только при синтаксической ошибке",
        "code": "mis-cond-else-syntax-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("e2494c05-49a7-474a-a149-000000000010"),
        "error_text": "Выбран вариант, связывающий else с синтаксической ошибкой.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, ветка else воспринимается "
            "как обработчик синтаксической ошибки."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Сравни назначение ветки else с тем, "
            "что происходит при синтаксической ошибке."
        ),
        "remediation_exercise_id": "conditions-v1",
    },
)


def _tables() -> tuple[sa.Table, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    misconceptions = sa.Table(
        "misconceptions",
        metadata,
        sa.Column("code", sa.String(120)),
        sa.Column("skill_id", sa.String(120)),
    )
    versions = sa.Table(
        "misconception_versions",
        metadata,
        sa.Column("id", sa.Uuid(as_uuid=True)),
        sa.Column("misconception_code", sa.String(120)),
        sa.Column("version", sa.Integer()),
        sa.Column("error_text", sa.Text()),
        sa.Column("typical_wrong_explanation", sa.Text()),
        sa.Column("remediation_text", sa.Text()),
        sa.Column("remediation_exercise_id", sa.String(80)),
        sa.Column("remediation_exercise_version", sa.Integer()),
    )
    mappings = sa.Table(
        "misconception_mappings",
        metadata,
        sa.Column("id", sa.Uuid(as_uuid=True)),
        sa.Column("source_type", sa.String(40)),
        sa.Column("exercise_id", sa.String(80)),
        sa.Column("exercise_version", sa.Integer()),
        sa.Column("question_id", sa.String(100)),
        sa.Column("wrong_choice", sa.Text()),
        sa.Column("misconception_code", sa.String(120)),
        sa.Column("misconception_version_id", sa.Uuid(as_uuid=True)),
    )
    return misconceptions, versions, mappings


def seed_assessment_mappings(connection: sa.Connection) -> None:
    misconceptions, versions, mappings = _tables()
    for index, item in enumerate(SEED_MAPPINGS, start=1):
        existing_misconception = connection.execute(
            sa.select(misconceptions).where(misconceptions.c.code == item["code"])
        ).mappings().first()
        if existing_misconception is None:
            connection.execute(
                misconceptions.insert().values(
                    code=item["code"],
                    skill_id=item["skill_id"],
                )
            )
        elif existing_misconception["skill_id"] != item["skill_id"]:
            raise RuntimeError(f"Misconception seed conflict: {item['code']}")

        if "error_text" in item:
            version_values = {
                "id": item["version_id"],
                "misconception_code": item["code"],
                "version": 1,
                "error_text": item["error_text"],
                "typical_wrong_explanation": item["typical_wrong_explanation"],
                "remediation_text": item["remediation_text"],
                "remediation_exercise_id": item["remediation_exercise_id"],
                "remediation_exercise_version": 1,
            }
            existing_version = connection.execute(
                sa.select(versions).where(
                    versions.c.misconception_code == item["code"],
                    versions.c.version == 1,
                )
            ).mappings().first()
            if existing_version is None:
                connection.execute(versions.insert().values(**version_values))
            elif any(
                existing_version[key] != value
                for key, value in version_values.items()
            ):
                raise RuntimeError(
                    f"Misconception version seed conflict: {item['code']} v1"
                )

        mapping_values = {
            "id": UUID(f"e2494c05-49a7-474a-a149-{index:012d}"),
            "source_type": item.get("source_type", "assessment_response"),
            "exercise_id": item["exercise_id"],
            "exercise_version": 1,
            "question_id": item["question_id"],
            "wrong_choice": item["wrong_choice"],
            "misconception_code": item["code"],
            "misconception_version_id": item["version_id"],
        }
        existing_mapping = connection.execute(
            sa.select(mappings).where(
                mappings.c.source_type == mapping_values["source_type"],
                mappings.c.exercise_id == mapping_values["exercise_id"],
                mappings.c.exercise_version == mapping_values["exercise_version"],
                mappings.c.question_id == mapping_values["question_id"],
                mappings.c.wrong_choice == mapping_values["wrong_choice"],
            )
        ).mappings().first()
        if existing_mapping is None:
            connection.execute(mappings.insert().values(**mapping_values))
        elif any(
            existing_mapping[key] != value
            for key, value in mapping_values.items()
        ):
            raise RuntimeError(
                "Assessment misconception mapping seed conflict: "
                f"{item['exercise_id']} / {item['wrong_choice']}"
            )


def upgrade() -> None:
    seed_assessment_mappings(op.get_bind())


def downgrade() -> None:
    connection = op.get_bind()
    _, versions, mappings = _tables()
    codes = sorted({item["code"] for item in SEED_MAPPINGS if "error_text" in item})
    occurrences = sa.table(
        "mistake_occurrences",
        sa.column("misconception_code", sa.String(120)),
    )
    misconceptions = sa.table(
        "misconceptions",
        sa.column("code", sa.String(120)),
    )
    for item in SEED_MAPPINGS:
        connection.execute(
            mappings.delete().where(
                mappings.c.source_type
                == item.get("source_type", "assessment_response"),
                mappings.c.exercise_id == item["exercise_id"],
                mappings.c.exercise_version == 1,
                mappings.c.question_id == item["question_id"],
                mappings.c.wrong_choice == item["wrong_choice"],
            )
        )
    for code in codes:
        has_occurrences = connection.scalar(
            sa.select(sa.literal(1))
            .select_from(occurrences)
            .where(occurrences.c.misconception_code == code)
            .limit(1)
        )
        if has_occurrences is None:
            connection.execute(
                versions.delete().where(
                    versions.c.misconception_code == code,
                    versions.c.version == 1,
                )
            )
            connection.execute(misconceptions.delete().where(misconceptions.c.code == code))
