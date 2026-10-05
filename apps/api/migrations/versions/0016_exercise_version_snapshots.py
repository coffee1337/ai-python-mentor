"""Persist exercise-version snapshots without changing historical hint reveals.

Downgrade retains populated snapshot associations in a compatibility table;
the next upgrade restores them after the v1 backfill. The table is only
removed once restoration succeeds. No historical hint-reveal row is rewritten.
"""

import sqlalchemy as sa
from alembic import op


revision = "0016_exercise_version_snapshots"
down_revision = "0015_exercise_hint_ladder"
branch_labels = None
depends_on = None


_DOWNGRADE_BACKUP_TABLE = "exercise_version_snapshot_downgrade"
_SOURCES = ("assessment_responses", "knowledge_check_attempts")


def _backup_table():
    return sa.table(
        _DOWNGRADE_BACKUP_TABLE,
        sa.column("source_table", sa.String(40)),
        sa.column("source_id", sa.Uuid(as_uuid=True)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
    )


def _source_table(name):
    return sa.table(
        name,
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
    )


def _restore_downgrade_backup(connection):
    inspector = sa.inspect(connection)
    if _DOWNGRADE_BACKUP_TABLE not in inspector.get_table_names():
        return

    backup = _backup_table()
    rows = connection.execute(sa.select(backup)).mappings()
    for row in rows:
        if row["source_table"] not in _SOURCES:
            raise ValueError("Unknown exercise snapshot backup source")
        source = _source_table(row["source_table"])
        connection.execute(
            sa.update(source)
            .where(source.c.id == row["source_id"])
            .values(exercise_version_id=row["exercise_version_id"]),
        )
    op.drop_table(_DOWNGRADE_BACKUP_TABLE)


def upgrade():
    with op.batch_alter_table("assessment_responses") as batch_op:
        batch_op.add_column(sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.create_index("ix_assessment_responses_exercise_version_id", ["exercise_version_id"])
        batch_op.create_foreign_key(
            "fk_assessment_responses_exercise_version_id",
            "exercise_versions",
            ["exercise_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("knowledge_check_attempts") as batch_op:
        batch_op.add_column(sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.create_index("ix_knowledge_check_attempts_exercise_version_id", ["exercise_version_id"])
        batch_op.create_foreign_key(
            "fk_knowledge_check_attempts_exercise_version_id",
            "exercise_versions",
            ["exercise_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE assessment_responses
            SET exercise_version_id = (
                SELECT exercise_versions.id
                FROM exercise_versions
                WHERE exercise_versions.exercise_id = assessment_responses.question_id
                  AND exercise_versions.version = 1
            )
            WHERE exercise_version_id IS NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE knowledge_check_attempts
            SET exercise_version_id = (
                SELECT exercise_versions.id
                FROM exercise_versions
                WHERE exercise_versions.exercise_id = knowledge_check_attempts.lesson_id
                  AND exercise_versions.version = 1
            )
            WHERE exercise_version_id IS NULL
            """
        )
    )
    _restore_downgrade_backup(connection)


def downgrade():
    # 0015 has no snapshot columns. Keep populated values in a small
    # compatibility table so downgrade -> upgrade does not discard the
    # associations created by 0016.
    op.create_table(
        _DOWNGRADE_BACKUP_TABLE,
        sa.Column("source_table", sa.String(40), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("source_table", "source_id"),
    )
    connection = op.get_bind()
    backup = _backup_table()
    for source_table in _SOURCES:
        source = _source_table(source_table)
        rows = connection.execute(
            sa.select(source.c.id, source.c.exercise_version_id).where(
                source.c.exercise_version_id.is_not(None)
            )
        ).mappings()
        for row in rows:
            connection.execute(
                backup.insert(),
                {
                    "source_table": source_table,
                    "source_id": row["id"],
                    "exercise_version_id": row["exercise_version_id"],
                },
            )

    with op.batch_alter_table("knowledge_check_attempts") as batch_op:
        batch_op.drop_constraint(
            "fk_knowledge_check_attempts_exercise_version_id",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_knowledge_check_attempts_exercise_version_id")
        batch_op.drop_column("exercise_version_id")

    with op.batch_alter_table("assessment_responses") as batch_op:
        batch_op.drop_constraint(
            "fk_assessment_responses_exercise_version_id",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_assessment_responses_exercise_version_id")
        batch_op.drop_column("exercise_version_id")
