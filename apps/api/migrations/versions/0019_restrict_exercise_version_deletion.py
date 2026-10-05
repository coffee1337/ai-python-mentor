"""Make published exercise versions append-only at the database boundary.

Historical hint rows, reveals, assessment bindings, and knowledge-check
sources must keep their exact version forever.  SQLite needs batch recreation
for changing foreign-key actions; PostgreSQL can use the same Alembic path.
"""

import sqlalchemy as sa
from alembic import op


revision = "0019_restrict_exercise_version_deletion"
down_revision = "0018_assessment_run_exercise_version"
branch_labels = None
depends_on = None


_VERSION_REFERENCES = (
    ("exercise_hints", "exercise_version_id", "CASCADE"),
    ("hint_reveals", "exercise_version_id", "CASCADE"),
    ("assessment_runs", "current_exercise_version_id", "SET NULL"),
    ("assessment_responses", "exercise_version_id", "SET NULL"),
    ("knowledge_check_attempts", "exercise_version_id", "SET NULL"),
)


def _set_version_fk_action(table_name: str, column_name: str, ondelete: str) -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=connection)
    matches = [
        constraint
        for constraint in table.foreign_key_constraints
        if constraint.referred_table.name == "exercise_versions"
        and {column.name for column in constraint.columns} == {column_name}
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one exercise_versions FK on {table_name}")
    constraint = matches[0]
    if connection.dialect.name == "sqlite":
        constraint.ondelete = ondelete
        with op.batch_alter_table(
            table_name,
            recreate="always",
            copy_from=table,
        ):
            pass
        return

    if constraint.name is None:
        raise RuntimeError(f"Expected a named exercise_versions FK on {table_name}")
    op.drop_constraint(constraint.name, table_name, type_="foreignkey")
    op.create_foreign_key(
        constraint.name,
        table_name,
        "exercise_versions",
        [column_name],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    for table_name, column_name, _ in _VERSION_REFERENCES:
        _set_version_fk_action(table_name, column_name, "RESTRICT")


def downgrade() -> None:
    for table_name, column_name, ondelete in reversed(_VERSION_REFERENCES):
        _set_version_fk_action(table_name, column_name, ondelete)
