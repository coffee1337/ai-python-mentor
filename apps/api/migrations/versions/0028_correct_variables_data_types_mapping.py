"""Separate variable and data-type lesson completion mappings."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op


revision = "0028_correct_variables_data_types_mapping"
down_revision = "0027_review_api"
branch_labels = None
depends_on = None

_VARIABLES_PRIMARY_ID = uuid.UUID("00280000-0000-4000-8000-000000000001")
_DATA_TYPES_ID = uuid.UUID("00280000-0000-4000-8000-000000000002")
_LEGACY_VARIABLES_TYPES_ID = uuid.UUID("00280000-0000-4000-8000-000000000003")


def _lesson_skills():
    return sa.table(
        "lesson_skills",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("lesson_id", sa.String(80)),
        sa.column("skill_id", sa.String(120)),
    )


def _ensure_skill(
    connection,
    *,
    skill_id: str,
    name: str,
    difficulty: float,
    description: str,
) -> None:
    skills = sa.table(
        "skills",
        sa.column("id", sa.String(120)),
        sa.column("name", sa.String(160)),
        sa.column("category", sa.String(120)),
        sa.column("difficulty", sa.Float()),
        sa.column("importance", sa.Float()),
        sa.column("tags", sa.JSON()),
        sa.column("description", sa.Text()),
    )
    if connection.execute(
        sa.select(skills.c.id).where(skills.c.id == skill_id)
    ).first() is None:
        # Clean schema upgrades may not have run the runtime skill-graph seed.
        # Add only the referenced node needed by the required lesson mapping;
        # the runtime seeder later applies the canonical graph fields.
        connection.execute(
            skills.insert().values(
                id=skill_id,
                name=name,
                category="python.core",
                difficulty=difficulty,
                importance=0.5,
                tags=[],
                description=description,
            )
        )


def _ensure_link(connection, table, *, lesson_id: str, skill_id: str, row_id) -> None:
    exists = connection.execute(
        sa.select(table.c.id).where(
            table.c.lesson_id == lesson_id,
            table.c.skill_id == skill_id,
        )
    ).first()
    if exists is None:
        connection.execute(
            table.insert().values(id=row_id, lesson_id=lesson_id, skill_id=skill_id)
        )


def upgrade() -> None:
    connection = op.get_bind()
    lesson_skills = _lesson_skills()
    _ensure_skill(
        connection,
        skill_id="python.variables",
        name="variables",
        difficulty=0.1,
        description="Python core skill: variables",
    )
    _ensure_skill(
        connection,
        skill_id="python.data_types",
        name="data types",
        difficulty=0.12,
        description="Python core skill: data types",
    )
    connection.execute(
        lesson_skills.delete().where(
            lesson_skills.c.lesson_id == "variables-v1",
            lesson_skills.c.skill_id == "python.data_types",
        )
    )
    _ensure_link(
        connection,
        lesson_skills,
        lesson_id="variables-v1",
        skill_id="python.variables",
        row_id=_VARIABLES_PRIMARY_ID,
    )
    _ensure_link(
        connection,
        lesson_skills,
        lesson_id="data-types-v1",
        skill_id="python.data_types",
        row_id=_DATA_TYPES_ID,
    )


def downgrade() -> None:
    connection = op.get_bind()
    lesson_skills = _lesson_skills()
    # Delete only links this migration itself may have inserted. Pre-existing
    # natural-key rows (if any) are retained.
    connection.execute(
        lesson_skills.delete().where(
            lesson_skills.c.id.in_((_VARIABLES_PRIMARY_ID, _DATA_TYPES_ID))
        )
    )
    _ensure_link(
        connection,
        lesson_skills,
        lesson_id="variables-v1",
        skill_id="python.data_types",
        row_id=_LEGACY_VARIABLES_TYPES_ID,
    )
