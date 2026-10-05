"""Add opaque review-session tokens and server-graded answer snapshots."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0027_review_api"
down_revision = "0026_review_scheduler"
branch_labels = None
depends_on = None

_BACKUP_SESSIONS = "review_api_downgrade_session_fields"
_BACKUP_ATTEMPTS = "review_api_downgrade_attempt_fields"


def upgrade() -> None:
    with op.batch_alter_table("review_sessions") as batch_op:
        batch_op.add_column(sa.Column("token_hash", sa.String(64), nullable=True))
        batch_op.create_check_constraint(
            "ck_review_session_token_hash_length",
            "token_hash IS NULL OR length(token_hash) = 64",
        )
    op.create_index(
        "ix_review_sessions_token_hash",
        "review_sessions",
        ["token_hash"],
        unique=True,
    )
    with op.batch_alter_table("review_attempts") as batch_op:
        batch_op.add_column(sa.Column("answers", sa.JSON(), nullable=True))
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if _BACKUP_SESSIONS in tables:
        sessions = sa.table(
            "review_sessions",
            sa.column("id", sa.Uuid()),
            sa.column("token_hash", sa.String(64)),
        )
        session_backup = sa.table(
            _BACKUP_SESSIONS,
            sa.column("id", sa.Uuid()),
            sa.column("token_hash", sa.String(64)),
        )
        for row in bind.execute(sa.select(session_backup)).mappings():
            bind.execute(
                sessions.update()
                .where(sessions.c.id == row["id"])
                .values(token_hash=row["token_hash"])
            )
        op.drop_table(_BACKUP_SESSIONS)
    if _BACKUP_ATTEMPTS in tables:
        attempts = sa.table(
            "review_attempts",
            sa.column("id", sa.Uuid()),
            sa.column("answers", sa.JSON()),
        )
        attempt_backup = sa.table(
            _BACKUP_ATTEMPTS,
            sa.column("id", sa.Uuid()),
            sa.column("answers", sa.JSON()),
        )
        for row in bind.execute(sa.select(attempt_backup)).mappings():
            bind.execute(
                attempts.update()
                .where(attempts.c.id == row["id"])
                .values(answers=row["answers"])
            )
        op.drop_table(_BACKUP_ATTEMPTS)


def downgrade() -> None:
    op.create_table(
        _BACKUP_SESSIONS,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64)),
    )
    op.create_table(
        _BACKUP_ATTEMPTS,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("answers", sa.JSON()),
    )
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"INSERT INTO {_BACKUP_SESSIONS} (id, token_hash) "
            "SELECT id, token_hash FROM review_sessions"
        )
    )
    bind.execute(
        sa.text(
            f"INSERT INTO {_BACKUP_ATTEMPTS} (id, answers) "
            "SELECT id, answers FROM review_attempts"
        )
    )
    with op.batch_alter_table("review_attempts") as batch_op:
        batch_op.drop_column("answers")
    op.drop_index("ix_review_sessions_token_hash", table_name="review_sessions")
    with op.batch_alter_table("review_sessions") as batch_op:
        batch_op.drop_constraint(
            "ck_review_session_token_hash_length",
            type_="check",
        )
        batch_op.drop_column("token_hash")
