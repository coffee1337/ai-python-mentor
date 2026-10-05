"""Bind in-progress assessment questions to their immutable exercise version."""

import sqlalchemy as sa
from alembic import op


revision = "0018_assessment_run_exercise_version"
down_revision = "0017_exercise_content_snapshots"
branch_labels = None
depends_on = None


_BACKUP_TABLE = "assessment_run_version_downgrade"
_ALEMBIC_VERSION_LENGTH = 128


def _runs_table():
    return sa.table(
        "assessment_runs",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("current_exercise_version_id", sa.Uuid(as_uuid=True)),
    )


def _backup_table():
    return sa.table(
        _BACKUP_TABLE,
        sa.column("assessment_run_id", sa.Uuid(as_uuid=True)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
    )


def _restore_downgrade_backup(connection):
    if _BACKUP_TABLE not in sa.inspect(connection).get_table_names():
        return
    runs = _runs_table()
    backup = _backup_table()
    for row in connection.execute(sa.select(backup)).mappings():
        connection.execute(
            runs.update()
            .where(runs.c.id == row["assessment_run_id"])
            .values(current_exercise_version_id=row["exercise_version_id"])
        )
    op.drop_table(_BACKUP_TABLE)


def _ensure_alembic_version_capacity():
    """Allow this and subsequent long revision ids before Alembic updates it."""

    with op.batch_alter_table("alembic_version") as batch_op:
        batch_op.alter_column(
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=_ALEMBIC_VERSION_LENGTH),
            existing_nullable=False,
        )


def upgrade():
    # Alembic writes revision 0018 only after this function returns.  Expand
    # the version column first so that the write is transactional and succeeds
    # on databases created with Alembic's default VARCHAR(32).
    _ensure_alembic_version_capacity()

    with op.batch_alter_table("assessment_runs") as batch_op:
        batch_op.add_column(
            sa.Column("current_exercise_version_id", sa.Uuid(as_uuid=True), nullable=True)
        )
        batch_op.create_index(
            "ix_assessment_runs_current_exercise_version_id",
            ["current_exercise_version_id"],
        )
        batch_op.create_foreign_key(
            "fk_assessment_runs_current_exercise_version_id",
            "exercise_versions",
            ["current_exercise_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _restore_downgrade_backup(op.get_bind())


def downgrade():
    # Keep the expanded capacity.  During this function Alembic still stores
    # the current 0018 revision (36 chars); shrinking here would fail on
    # PostgreSQL before Alembic can record 0017.  The wider type is harmless
    # and is required again when upgrading back through 0018.
    op.create_table(
        _BACKUP_TABLE,
        sa.Column("assessment_run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("assessment_run_id"),
    )
    connection = op.get_bind()
    runs = _runs_table()
    backup = _backup_table()
    for row in connection.execute(
        sa.select(runs.c.id, runs.c.current_exercise_version_id).where(
            runs.c.current_exercise_version_id.is_not(None)
        )
    ).mappings():
        connection.execute(
            backup.insert().values(
                assessment_run_id=row["id"],
                exercise_version_id=row["current_exercise_version_id"],
            )
        )

    with op.batch_alter_table("assessment_runs") as batch_op:
        batch_op.drop_constraint(
            "fk_assessment_runs_current_exercise_version_id",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_assessment_runs_current_exercise_version_id")
        batch_op.drop_column("current_exercise_version_id")
