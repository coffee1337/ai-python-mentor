"""Add versioned misconception catalog and idempotent learner mistake memory."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from alembic import op


revision = "0023_mistake_memory"
down_revision = "0022_lesson_sessions"
branch_labels = None
depends_on = None


# Authored misconception entries are seeded together with their exact,
# versioned wrong-choice mappings in the following migration. This schema
# revision intentionally does not invent an unclassified misconception.
SEED_CATALOG: tuple[dict, ...] = ()


def _catalog_tables() -> tuple[sa.Table, sa.Table]:
    misconceptions = sa.table(
        "misconceptions",
        sa.column("code", sa.String(120)),
        sa.column("skill_id", sa.String(120)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    versions = sa.table(
        "misconception_versions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("misconception_code", sa.String(120)),
        sa.column("version", sa.Integer()),
        sa.column("error_text", sa.Text()),
        sa.column("typical_wrong_explanation", sa.Text()),
        sa.column("remediation_text", sa.Text()),
        sa.column("remediation_exercise_id", sa.String(80)),
        sa.column("remediation_exercise_version", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    return misconceptions, versions


def seed_misconception_catalog(connection: sa.Connection) -> None:
    """Insert only missing, immutable seed rows; reject content drift."""

    misconceptions, versions = _catalog_tables()
    for item in SEED_CATALOG:
        existing = connection.execute(
            sa.select(misconceptions).where(misconceptions.c.code == item["code"])
        ).mappings().first()
        if existing is None:
            connection.execute(
                misconceptions.insert().values(
                    code=item["code"],
                    skill_id=item["skill_id"],
                )
            )
        elif existing["skill_id"] != item["skill_id"]:
            raise RuntimeError(f"Misconception seed conflict: {item['code']}")

        expected = {
            "id": item["version_id"],
            "misconception_code": item["code"],
            "version": item["version"],
            "error_text": item["error_text"],
            "typical_wrong_explanation": item["typical_wrong_explanation"],
            "remediation_text": item["remediation_text"],
            "remediation_exercise_id": item["remediation_exercise_id"],
            "remediation_exercise_version": item["remediation_exercise_version"],
        }
        existing_version = connection.execute(
            sa.select(versions).where(
                versions.c.misconception_code == item["code"],
                versions.c.version == item["version"],
            )
        ).mappings().first()
        if existing_version is None:
            connection.execute(versions.insert().values(**expected))
        elif any(existing_version[key] != value for key, value in expected.items()):
            raise RuntimeError(
                f"Misconception version seed conflict: {item['code']} v{item['version']}"
            )


def upgrade() -> None:
    op.create_table(
        "misconceptions",
        sa.Column("code", sa.String(120), primary_key=True),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", "skill_id", name="uq_misconception_code_skill"),
    )
    op.create_table(
        "misconception_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("misconception_code", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=False),
        sa.Column("typical_wrong_explanation", sa.Text(), nullable=False),
        sa.Column("remediation_text", sa.Text(), nullable=False),
        sa.Column("remediation_exercise_id", sa.String(80), nullable=False),
        sa.Column("remediation_exercise_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["misconception_code"],
            ["misconceptions.code"],
            name="fk_misconception_versions_code",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("misconception_code", "version", name="uq_misconception_version"),
        sa.UniqueConstraint("id", "misconception_code", name="uq_misconception_version_id_code"),
        sa.CheckConstraint("version >= 1", name="ck_misconception_version_positive"),
        sa.CheckConstraint(
            "remediation_exercise_version >= 1",
            name="ck_misconception_remediation_exercise_version_positive",
        ),
    )
    op.create_index(
        "ix_misconception_versions_misconception_code",
        "misconception_versions",
        ["misconception_code"],
    )

    op.create_table(
        "user_mistakes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("misconception_code", sa.String(120), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("lesson_id", sa.String(80)),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_source_type", sa.String(40), nullable=False),
        sa.Column("last_source_id", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_mistakes_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["misconception_code", "skill_id"],
            ["misconceptions.code", "misconceptions.skill_id"],
            name="fk_user_mistakes_misconception_skill",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "misconception_code", name="uq_user_mistake_user_code"),
        sa.UniqueConstraint("id", "user_id", "misconception_code", name="uq_user_mistake_id_user_code"),
        sa.CheckConstraint("occurrence_count >= 1", name="ck_user_mistake_count_positive"),
        sa.CheckConstraint("first_seen_at <= last_seen_at", name="ck_user_mistake_seen_order"),
    )
    op.create_index("ix_user_mistakes_user_id", "user_mistakes", ["user_id"])
    op.create_index("ix_user_mistakes_skill_id", "user_mistakes", ["skill_id"])

    op.create_table(
        "mistake_occurrences",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_mistake_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("misconception_code", sa.String(120), nullable=False),
        sa.Column("misconception_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("lesson_id", sa.String(80)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_mistake_occurrences_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["misconception_code"],
            ["misconceptions.code"],
            name="fk_mistake_occurrences_misconception_code",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_mistake_id", "user_id", "misconception_code"],
            ["user_mistakes.id", "user_mistakes.user_id", "user_mistakes.misconception_code"],
            name="fk_mistake_occurrences_user_mistake_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["misconception_version_id", "misconception_code"],
            ["misconception_versions.id", "misconception_versions.misconception_code"],
            name="fk_mistake_occurrences_version_code",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "misconception_code",
            name="uq_mistake_occurrence_source",
        ),
        sa.CheckConstraint(
            "source_type IN ('knowledge_check_response', 'assessment_response', 'coding_attempt')",
            name="ck_mistake_occurrence_source_type",
        ),
    )
    op.create_index("ix_mistake_occurrences_user_id", "mistake_occurrences", ["user_id"])
    op.create_index(
        "ix_mistake_occurrences_misconception_code",
        "mistake_occurrences",
        ["misconception_code"],
    )

    seed_misconception_catalog(op.get_bind())


def downgrade() -> None:
    op.drop_index("ix_mistake_occurrences_misconception_code", table_name="mistake_occurrences")
    op.drop_index("ix_mistake_occurrences_user_id", table_name="mistake_occurrences")
    op.drop_table("mistake_occurrences")
    op.drop_index("ix_user_mistakes_skill_id", table_name="user_mistakes")
    op.drop_index("ix_user_mistakes_user_id", table_name="user_mistakes")
    op.drop_table("user_mistakes")
    op.drop_index("ix_misconception_versions_misconception_code", table_name="misconception_versions")
    op.drop_table("misconception_versions")
    op.drop_table("misconceptions")
