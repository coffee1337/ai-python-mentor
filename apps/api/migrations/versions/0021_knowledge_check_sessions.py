"""Bind knowledge-check GET/POST flows to one immutable exercise version."""

import sqlalchemy as sa
from alembic import op


revision = "0021_knowledge_check_sessions"
down_revision = "0020_skill_evidence_assistance_constraints"
branch_labels = None
depends_on = None

_BACKUP_TABLE = "knowledge_check_session_downgrade"


def _sessions_table():
    return sa.table(
        "knowledge_check_sessions",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("user_id", sa.Uuid(as_uuid=True)),
        sa.column("lesson_id", sa.String(80)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("consumed_at", sa.DateTime(timezone=True)),
    )


def _backup_table():
    return sa.table(
        _BACKUP_TABLE,
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("user_id", sa.Uuid(as_uuid=True)),
        sa.column("lesson_id", sa.String(80)),
        sa.column("exercise_version_id", sa.Uuid(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("consumed_at", sa.DateTime(timezone=True)),
    )


def _restore_downgrade_backup(connection):
    if _BACKUP_TABLE not in sa.inspect(connection).get_table_names():
        return
    sessions = _sessions_table()
    backup = _backup_table()
    for row in connection.execute(sa.select(backup)).mappings():
        connection.execute(sessions.insert().values(**row))
    op.drop_table(_BACKUP_TABLE)


def upgrade() -> None:
    op.create_table(
        "knowledge_check_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_version_id"], ["exercise_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_check_sessions_user_id",
        "knowledge_check_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_knowledge_check_sessions_lesson_id",
        "knowledge_check_sessions",
        ["lesson_id"],
    )
    op.create_index(
        "ix_knowledge_check_sessions_exercise_version_id",
        "knowledge_check_sessions",
        ["exercise_version_id"],
    )
    op.create_index(
        "uq_knowledge_check_session_pending",
        "knowledge_check_sessions",
        ["user_id", "lesson_id"],
        unique=True,
        sqlite_where=sa.text("consumed_at IS NULL"),
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    _restore_downgrade_backup(op.get_bind())


def downgrade() -> None:
    op.create_table(
        _BACKUP_TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
    )
    connection = op.get_bind()
    sessions = _sessions_table()
    backup = _backup_table()
    for row in connection.execute(sa.select(sessions)).mappings():
        connection.execute(backup.insert().values(**row))

    op.drop_index(
        "uq_knowledge_check_session_pending",
        table_name="knowledge_check_sessions",
    )
    op.drop_index(
        "ix_knowledge_check_sessions_exercise_version_id",
        table_name="knowledge_check_sessions",
    )
    op.drop_index(
        "ix_knowledge_check_sessions_lesson_id",
        table_name="knowledge_check_sessions",
    )
    op.drop_index(
        "ix_knowledge_check_sessions_user_id",
        table_name="knowledge_check_sessions",
    )
    op.drop_table("knowledge_check_sessions")
