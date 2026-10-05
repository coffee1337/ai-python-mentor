"""Bind lesson display and grading to an immutable exercise version."""

import sqlalchemy as sa
from alembic import op


revision = "0022_lesson_sessions"
down_revision = "0021_knowledge_check_sessions"
branch_labels = None
depends_on = None

_BACKUP_TABLE = "lesson_session_downgrade"


def _sessions():
    return sa.table(
        "lesson_sessions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("user_id", sa.Uuid(as_uuid=True)),
        sa.column("lesson_id", sa.String(80)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("consumed_at", sa.DateTime(timezone=True)),
    )


def _backup():
    return sa.table(
        _BACKUP_TABLE,
        sa.column("kind", sa.String(20)),
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("user_id", sa.Uuid(as_uuid=True)),
        sa.column("lesson_id", sa.String(80)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("consumed_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    op.create_table(
        "lesson_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), sa.ForeignKey("exercise_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_lesson_sessions_user_id", "lesson_sessions", ["user_id"])
    op.create_index("ix_lesson_sessions_lesson_id", "lesson_sessions", ["lesson_id"])
    op.create_index("ix_lesson_sessions_exercise_version_id", "lesson_sessions", ["exercise_version_id"])
    op.create_index(
        "uq_lesson_session_pending", "lesson_sessions", ["user_id", "lesson_id"],
        unique=True, sqlite_where=sa.text("consumed_at IS NULL"),
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    with op.batch_alter_table("lesson_completions") as batch:
        batch.add_column(sa.Column("exercise_version_id", sa.Uuid(as_uuid=True)))
        batch.create_index("ix_lesson_completions_exercise_version_id", ["exercise_version_id"])
        batch.create_foreign_key(
            "fk_lesson_completions_exercise_version_id", "exercise_versions",
            ["exercise_version_id"], ["id"], ondelete="RESTRICT",
        )

    connection = op.get_bind()
    if _BACKUP_TABLE in sa.inspect(connection).get_table_names():
        completions = sa.table(
            "lesson_completions",
            sa.column("user_id", sa.Uuid(as_uuid=True)),
            sa.column("lesson_id", sa.String(80)),
            sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
        )
        for row in connection.execute(sa.select(_backup())).mappings():
            if row["kind"] == "session":
                connection.execute(_sessions().insert().values(
                    id=row["id"], user_id=row["user_id"], lesson_id=row["lesson_id"],
                    exercise_version_id=row["exercise_version_id"],
                    created_at=row["created_at"], consumed_at=row["consumed_at"],
                ))
            elif row["kind"] == "completion":
                connection.execute(
                    completions.update().where(
                        completions.c.user_id == row["user_id"],
                        completions.c.lesson_id == row["lesson_id"],
                    ).values(exercise_version_id=row["exercise_version_id"])
                )
            else:
                raise ValueError("Unknown lesson binding backup kind")
        op.drop_table(_BACKUP_TABLE)


def downgrade() -> None:
    op.create_table(
        _BACKUP_TABLE,
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("kind", "id", "lesson_id"),
    )
    connection = op.get_bind()
    backup = _backup()
    for row in connection.execute(sa.select(_sessions())).mappings():
        connection.execute(backup.insert().values(kind="session", **row))
    completions = sa.table(
        "lesson_completions",
        sa.column("user_id", sa.Uuid(as_uuid=True)),
        sa.column("lesson_id", sa.String(80)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
    )
    for row in connection.execute(
        sa.select(completions).where(completions.c.exercise_version_id.is_not(None))
    ).mappings():
        connection.execute(backup.insert().values(
            kind="completion", id=row["user_id"], user_id=row["user_id"],
            lesson_id=row["lesson_id"], exercise_version_id=row["exercise_version_id"],
        ))

    with op.batch_alter_table("lesson_completions") as batch:
        batch.drop_constraint("fk_lesson_completions_exercise_version_id", type_="foreignkey")
        batch.drop_index("ix_lesson_completions_exercise_version_id")
        batch.drop_column("exercise_version_id")
    op.drop_index("uq_lesson_session_pending", table_name="lesson_sessions")
    op.drop_index("ix_lesson_sessions_exercise_version_id", table_name="lesson_sessions")
    op.drop_index("ix_lesson_sessions_lesson_id", table_name="lesson_sessions")
    op.drop_index("ix_lesson_sessions_user_id", table_name="lesson_sessions")
    op.drop_table("lesson_sessions")
