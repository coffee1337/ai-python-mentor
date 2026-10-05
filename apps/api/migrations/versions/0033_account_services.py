"""Durable account recovery, preferences, delivery and billing state.

Only new tables are introduced. Rollback removes these features' new state,
without changing users, sessions or any existing learning data.
"""
import sqlalchemy as sa
from alembic import op

revision = "0033_account_services"
down_revision = "0032_domain_admission"
branch_labels = None
depends_on = None


def _user_column(*, primary_key=False):
    return sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=primary_key, nullable=False)


def _id_column():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _created_column():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade():
    op.create_table("account_tokens", _id_column(), _user_column(),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True), _created_column(),
        sa.CheckConstraint("purpose IN ('email_verify','password_reset','telegram_bind')", name="ck_account_token_purpose"))
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_table("auth_throttle", sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_auth_throttle_attempts"))
    op.create_index("ix_auth_throttle_window_start", "auth_throttle", ["window_start"])
    op.create_table("notification_preferences", _user_column(primary_key=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("telegram_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("review_reminders", sa.Boolean(), nullable=False, server_default="true"))
    op.create_table("telegram_bindings", _user_column(primary_key=True),
        sa.Column("chat_id", sa.String(32), nullable=False, unique=True), _created_column())
    op.create_table("notification_outbox", _id_column(), _user_column(),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("template", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _created_column(), sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("channel IN ('email','telegram')", name="ck_notification_channel"),
        sa.CheckConstraint("status IN ('pending','delivering','delivered','cancelled','failed')", name="ck_notification_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_notification_attempts"))
    op.create_index("ix_notification_outbox_user_id", "notification_outbox", ["user_id"])
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])
    op.create_table("account_subscriptions", _user_column(primary_key=True),
        sa.Column("plan_id", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("plan_id IN ('free','pro')", name="ck_subscription_plan"),
        sa.CheckConstraint("status IN ('active','cancelled','expired')", name="ck_subscription_status"))
    op.create_table("billing_events", sa.Column("event_id", sa.String(80), primary_key=True), _user_column(),
        sa.Column("payload_digest", sa.String(64), nullable=False), _created_column())
    op.create_index("ix_billing_events_user_id", "billing_events", ["user_id"])
    op.create_table("admin_audit", _id_column(),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False), sa.Column("result_count", sa.Integer(), nullable=False), _created_column())
    op.create_index("ix_admin_audit_actor_id", "admin_audit", ["actor_id"])
    op.create_index("ix_admin_audit_target_id", "admin_audit", ["target_id"])


def downgrade():
    for table in ("admin_audit", "billing_events", "account_subscriptions", "notification_outbox",
                  "telegram_bindings", "notification_preferences", "auth_throttle", "account_tokens"):
        op.drop_table(table)
