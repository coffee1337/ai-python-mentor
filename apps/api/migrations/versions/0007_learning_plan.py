"""Persist personalized learning plans and ordered lesson recommendations."""
import sqlalchemy as sa
from alembic import op
revision="0007_learning_plan"
down_revision="0006_adaptive_assessment"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("learning_plans",sa.Column("id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("user_id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("assessment_run_id",sa.Uuid(as_uuid=True),nullable=True),sa.Column("focus_skill_id",sa.String(120)),sa.Column("recommendation_text",sa.Text(),nullable=False),sa.Column("version",sa.Integer(),server_default="1",nullable=False),sa.Column("generated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["assessment_run_id"],["assessment_runs.id"],ondelete="SET NULL"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("user_id"))
 op.create_table("learning_plan_items",sa.Column("id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("plan_id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("lesson_id",sa.String(80),nullable=False),sa.Column("skill_id",sa.String(120),nullable=False),sa.Column("position",sa.Integer(),nullable=False),sa.Column("focus_score",sa.Float(),nullable=False),sa.Column("rationale",sa.Text(),nullable=False),sa.ForeignKeyConstraint(["plan_id"],["learning_plans.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("plan_id","lesson_id",name="uq_learning_plan_lesson"))
 op.create_index("ix_learning_plan_items_plan_id","learning_plan_items",["plan_id"])
def downgrade():
 op.drop_index("ix_learning_plan_items_plan_id",table_name="learning_plan_items")
 op.drop_table("learning_plan_items")
 op.drop_table("learning_plans")
