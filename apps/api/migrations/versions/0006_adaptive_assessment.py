"""Add owned assessment runs and diagnostic answer evidence."""
import sqlalchemy as sa
from alembic import op
revision="0006_adaptive_assessment"
down_revision="0005_coding_attempts"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("assessment_runs",sa.Column("id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("user_id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("status",sa.String(20),server_default="in_progress",nullable=False),sa.Column("current_question_id",sa.String(80)),sa.Column("asked_question_ids",sa.Text(),nullable=False),sa.Column("completed_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
 op.create_index("ix_assessment_runs_user_id","assessment_runs",["user_id"])
 op.create_table("assessment_responses",sa.Column("id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("run_id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("question_id",sa.String(80),nullable=False),sa.Column("skill_id",sa.String(120),nullable=False),sa.Column("difficulty",sa.Float(),nullable=False),sa.Column("answer",sa.String(200),nullable=False),sa.Column("is_correct",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(["run_id"],["assessment_runs.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("run_id","question_id",name="uq_assessment_run_question"))
 op.create_index("ix_assessment_responses_run_id","assessment_responses",["run_id"])
def downgrade():
 op.drop_index("ix_assessment_responses_run_id",table_name="assessment_responses")
 op.drop_table("assessment_responses")
 op.drop_index("ix_assessment_runs_user_id",table_name="assessment_runs")
 op.drop_table("assessment_runs")
