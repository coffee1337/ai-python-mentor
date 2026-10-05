"""Persist owned end-of-lesson knowledge checks."""
import sqlalchemy as sa
from alembic import op
revision="0008_knowledge_checks"
down_revision="0007_learning_plan"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("knowledge_check_attempts",sa.Column("id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("user_id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("lesson_id",sa.String(80),nullable=False),sa.Column("skill_id",sa.String(120),nullable=False),sa.Column("score",sa.Float(),nullable=False),sa.Column("passed",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
 op.create_index("ix_knowledge_check_attempts_user_id","knowledge_check_attempts",["user_id"])
 op.create_index("ix_knowledge_check_attempts_lesson_id","knowledge_check_attempts",["lesson_id"])
 op.create_table("knowledge_check_responses",sa.Column("id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("attempt_id",sa.Uuid(as_uuid=True),nullable=False),sa.Column("question_id",sa.String(100),nullable=False),sa.Column("answer",sa.String(200),nullable=False),sa.Column("is_correct",sa.Boolean(),nullable=False),sa.Column("explanation",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(["attempt_id"],["knowledge_check_attempts.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
 op.create_index("ix_knowledge_check_responses_attempt_id","knowledge_check_responses",["attempt_id"])
def downgrade():
 op.drop_index("ix_knowledge_check_responses_attempt_id",table_name="knowledge_check_responses")
 op.drop_table("knowledge_check_responses")
 op.drop_index("ix_knowledge_check_attempts_lesson_id",table_name="knowledge_check_attempts")
 op.drop_index("ix_knowledge_check_attempts_user_id",table_name="knowledge_check_attempts")
 op.drop_table("knowledge_check_attempts")
