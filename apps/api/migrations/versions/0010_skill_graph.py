"""Add the Python Backend Skill Graph and lesson links."""
import sqlalchemy as sa
from alembic import op

revision = "0010_skill_graph"
down_revision = "0009_user_skills"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "skills",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("difficulty", sa.Float(), server_default="0", nullable=False),
        sa.Column("importance", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("tags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "skill_edges",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("from_skill_id", sa.String(120), nullable=False),
        sa.Column("to_skill_id", sa.String(120), nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["from_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("from_skill_id", "to_skill_id", "relation", name="uq_skill_edge"),
        sa.CheckConstraint("from_skill_id <> to_skill_id", name="ck_skill_edge_not_self"),
        sa.CheckConstraint(
            "relation IN ('prerequisite', 'related', 'specialization')",
            name="ck_skill_edge_relation",
        ),
    )
    op.create_index("ix_skill_edges_from_skill_id", "skill_edges", ["from_skill_id"])
    op.create_index("ix_skill_edges_to_skill_id", "skill_edges", ["to_skill_id"])
    op.create_table(
        "lesson_skills",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("lesson_id", sa.String(80), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("lesson_id", "skill_id", name="uq_lesson_skill"),
    )
    op.create_index("ix_lesson_skills_lesson_id", "lesson_skills", ["lesson_id"])
    op.create_index("ix_lesson_skills_skill_id", "lesson_skills", ["skill_id"])


def downgrade():
    op.drop_index("ix_lesson_skills_skill_id", table_name="lesson_skills")
    op.drop_index("ix_lesson_skills_lesson_id", table_name="lesson_skills")
    op.drop_table("lesson_skills")
    op.drop_index("ix_skill_edges_to_skill_id", table_name="skill_edges")
    op.drop_index("ix_skill_edges_from_skill_id", table_name="skill_edges")
    op.drop_table("skill_edges")
    op.drop_table("skills")
