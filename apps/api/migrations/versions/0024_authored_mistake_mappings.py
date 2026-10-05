"""Add exact authored wrong-choice mappings for Mistake Memory."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from alembic import op


revision = "0024_authored_mistake_mappings"
down_revision = "0023_mistake_memory"
branch_labels = None
depends_on = None


SEED_MAPPINGS = (
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "variables-v1",
        "exercise_version": 1,
        "question_id": "variables-output-v1",
        "wrong_choice": "4",
        "code": "mis-var-output-first-v1",
        "skill_id": "python.variables",
        "version_id": UUID("d2494c05-49a7-474a-a149-000000000001"),
        "error_text": "Выбран вариант «4» вместо результата последовательных присваиваний.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, ответ фиксирует первое значение "
            "count и не учитывает последующее присваивание."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Выпиши значение count после каждой строки, "
            "затем сопоставь его со значением в момент вызова print."
        ),
        "remediation_exercise_id": "variables-v1",
        "mapping_id": UUID("d2494c05-49a7-474a-a149-100000000001"),
    },
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "variables-v1",
        "exercise_version": 1,
        "question_id": "variables-output-v1",
        "wrong_choice": "2",
        "code": "mis-var-output-partial-v1",
        "skill_id": "python.variables",
        "version_id": UUID("d2494c05-49a7-474a-a149-000000000002"),
        "error_text": "Выбран вариант «2» вместо результата последовательных присваиваний.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, внимание сосредоточено на прибавке "
            "2 без учёта исходного значения count."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Проследи обе строки по порядку и запиши, "
            "чему равно count в момент вызова print."
        ),
        "remediation_exercise_id": "variables-v1",
        "mapping_id": UUID("d2494c05-49a7-474a-a149-100000000002"),
    },
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "variables-v1",
        "exercise_version": 1,
        "question_id": "variables-reassignment-v1",
        "wrong_choice": "Создаёт вторую переменную x",
        "code": "mis-var-reassign-second-v1",
        "skill_id": "python.variables",
        "version_id": UUID("d2494c05-49a7-474a-a149-000000000003"),
        "error_text": "Выбран вариант о создании второй переменной x.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, имя x слева при повторном "
            "присваивании воспринимается как новое имя."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Проверь, сколько имён x доступно после "
            "присваивания, и проследи, откуда берётся значение правой части."
        ),
        "remediation_exercise_id": "variables-v1",
        "mapping_id": UUID("d2494c05-49a7-474a-a149-100000000003"),
    },
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "variables-v1",
        "exercise_version": 1,
        "question_id": "variables-reassignment-v1",
        "wrong_choice": "Сравнивает x с 1",
        "code": "mis-var-reassign-compare-v1",
        "skill_id": "python.variables",
        "version_id": UUID("d2494c05-49a7-474a-a149-000000000004"),
        "error_text": "Выбран вариант о сравнении x с 1 при присваивании.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, оператор присваивания смешивается "
            "с проверкой равенства."
        ),
        "remediation_text": (
            "Вернись к variables-v1. Сравни запись присваивания и проверки "
            "равенства по символам, затем проследи, меняется ли x."
        ),
        "remediation_exercise_id": "variables-v1",
        "mapping_id": UUID("d2494c05-49a7-474a-a149-100000000004"),
    },
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "conditions-v1",
        "exercise_version": 1,
        "question_id": "conditions-boundary-v1",
        "wrong_choice": "Обе",
        "code": "mis-cond-boundary-both-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("d2494c05-49a7-474a-a149-000000000005"),
        "error_text": "Выбран вариант «Обе» для граничного значения условия.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, граничное значение связывается "
            "с выполнением обеих взаимоисключающих веток."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Подставь age = 18 в условие и определи, "
            "сколько веток выполняется в конструкции if/else."
        ),
        "remediation_exercise_id": "conditions-v1",
        "mapping_id": UUID("d2494c05-49a7-474a-a149-100000000005"),
    },
    {
        "source_type": "knowledge_check_response",
        "exercise_id": "conditions-v1",
        "exercise_version": 1,
        "question_id": "conditions-else-v1",
        "wrong_choice": "Всегда после if",
        "code": "mis-cond-else-always-v1",
        "skill_id": "python.conditionals",
        "version_id": UUID("d2494c05-49a7-474a-a149-000000000006"),
        "error_text": "Выбран вариант о безусловном выполнении ветки else.",
        "typical_wrong_explanation": (
            "Гипотеза, а не диагноз: возможно, else воспринимается как "
            "безусловное продолжение if."
        ),
        "remediation_text": (
            "Вернись к conditions-v1. Возьми пример с истинным условием if "
            "и проверь, выполняется ли в нём ветка else."
        ),
        "remediation_exercise_id": "conditions-v1",
        "mapping_id": UUID("d2494c05-49a7-474a-a149-100000000006"),
    },
)


def _catalog_tables(connection: sa.Connection) -> tuple[sa.Table, sa.Table]:
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
    return misconceptions, versions


def seed_authored_mappings(connection: sa.Connection) -> None:
    """Seed immutable catalog text and exact wrong-choice mappings idempotently."""

    misconceptions, versions = _catalog_tables(connection)
    mappings = sa.Table(
        "misconception_mappings",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(as_uuid=True)),
        sa.Column("source_type", sa.String(40)),
        sa.Column("exercise_id", sa.String(80)),
        sa.Column("exercise_version", sa.Integer()),
        sa.Column("question_id", sa.String(100)),
        sa.Column("wrong_choice", sa.Text()),
        sa.Column("misconception_code", sa.String(120)),
        sa.Column("misconception_version_id", sa.Uuid(as_uuid=True)),
    )
    for item in SEED_MAPPINGS:
        existing_misconception = connection.execute(
            sa.select(misconceptions).where(misconceptions.c.code == item["code"])
        ).mappings().first()
        if existing_misconception is None:
            connection.execute(
                misconceptions.insert().values(code=item["code"], skill_id=item["skill_id"])
            )
        elif existing_misconception["skill_id"] != item["skill_id"]:
            raise RuntimeError(f"Misconception seed conflict: {item['code']}")

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
        elif any(existing_version[key] != value for key, value in version_values.items()):
            raise RuntimeError(f"Misconception version seed conflict: {item['code']} v1")

        mapping_values = {
            "id": item["mapping_id"],
            "source_type": item["source_type"],
            "exercise_id": item["exercise_id"],
            "exercise_version": item["exercise_version"],
            "question_id": item["question_id"],
            "wrong_choice": item["wrong_choice"],
            "misconception_code": item["code"],
            "misconception_version_id": item["version_id"],
        }
        existing_mapping = connection.execute(
            sa.select(mappings).where(
                mappings.c.source_type == item["source_type"],
                mappings.c.exercise_id == item["exercise_id"],
                mappings.c.exercise_version == item["exercise_version"],
                mappings.c.question_id == item["question_id"],
                mappings.c.wrong_choice == item["wrong_choice"],
            )
        ).mappings().first()
        if existing_mapping is None:
            connection.execute(mappings.insert().values(**mapping_values))
        elif any(existing_mapping[key] != value for key, value in mapping_values.items()):
            raise RuntimeError(
                "Authored misconception mapping conflict: "
                f"{item['exercise_id']} v{item['exercise_version']} "
                f"{item['question_id']} / {item['wrong_choice']}"
            )


def upgrade() -> None:
    op.create_table(
        "misconception_mappings",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("exercise_id", sa.String(80), nullable=False),
        sa.Column("exercise_version", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("wrong_choice", sa.Text(), nullable=False),
        sa.Column("misconception_code", sa.String(120), nullable=False),
        sa.Column("misconception_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["misconception_version_id", "misconception_code"],
            ["misconception_versions.id", "misconception_versions.misconception_code"],
            name="fk_misconception_mapping_version_code",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "exercise_id",
            "exercise_version",
            "question_id",
            "wrong_choice",
            name="uq_misconception_mapping_authored_choice",
        ),
        sa.CheckConstraint(
            "source_type IN ('knowledge_check_response', 'assessment_response')",
            name="ck_misconception_mapping_source_type",
        ),
        sa.CheckConstraint(
            "exercise_version >= 1",
            name="ck_misconception_mapping_exercise_version",
        ),
    )
    seed_authored_mappings(op.get_bind())


def downgrade() -> None:
    # Keep versioned catalog rows: recorded mistakes may still reference them.
    op.drop_table("misconception_mappings")
