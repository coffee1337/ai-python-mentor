"""Persist structured per-user skill mastery evidence."""
import sqlalchemy as sa
from alembic import op
revision="0009_user_skills"
down_revision="0008_knowledge_checks"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("user_skills",sa.Column("id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("user_id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("skill_id",sa.String(120),nullable=False),sa.Column("knowledge_score",sa.Float(),server_default="0",nullable=False),sa.Column("practice_score",sa.Float(),server_default="0",nullable=False),sa.Column("independent_score",sa.Float(),server_default="0",nullable=False),sa.Column("retention_score",sa.Float(),server_default="0",nullable=False),sa.Column("confidence",sa.Float(),server_default="0",nullable=False),sa.Column("evidence_count",sa.Integer(),server_default="0",nullable=False),sa.Column("last_practiced_at",sa.DateTime(timezone=True)),sa.Column("next_review_at",sa.DateTime(timezone=True)),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("user_id","skill_id",name="uq_user_skill"))
 op.create_index("ix_user_skills_user_id","user_skills",["user_id"])
def downgrade():
 op.drop_index("ix_user_skills_user_id",table_name="user_skills")
 op.drop_table("user_skills")
