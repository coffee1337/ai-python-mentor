"""Add the skill- and version-scoped knowledge chunk index.

The index stores embeddings as packed float32 bytes rather than through
pgvector. That keeps `alembic upgrade head` working on a developer machine
where the extension is not installed, adds no dependency, and keeps the column
opaque to the storage engine. Ranking happens in the domain, which also lets
retrieval degrade instead of failing when embeddings are absent.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_knowledge_chunks"
down_revision = "0030_bind_submission_results_to_exercise_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("exercise_version_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(120), nullable=False),
        sa.Column("section", sa.String(32), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_digest", sa.String(80), nullable=False),
        sa.Column("char_count", sa.Integer, nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(120), nullable=True),
        sa.Column("embedding_digest", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["exercise_version_id"], ["exercise_versions.id"], ondelete="CASCADE",
            name="fk_knowledge_chunks_exercise_version_id",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], ondelete="CASCADE",
            name="fk_knowledge_chunks_skill_id",
        ),
        sa.UniqueConstraint(
            "exercise_version_id", "section", "ordinal", name="uq_knowledge_chunk_position",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_knowledge_chunk_ordinal"),
        sa.CheckConstraint("char_count > 0 AND char_count <= 4000", name="ck_knowledge_chunk_size"),
        sa.CheckConstraint(
            "section IN ('goal', 'theory', 'body', 'example', 'example_output', "
            "'conclusion', 'practice', 'checkpoint', 'misconception_check')",
            name="ck_knowledge_chunk_section_kind",
        ),
        sa.CheckConstraint(
            "embedding IS NULL OR embedding_dim IS NOT NULL",
            name="ck_knowledge_chunk_embedding_dim",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_exercise_version_id",
        "knowledge_chunks",
        ["exercise_version_id"],
    )
    op.create_index("ix_knowledge_chunks_skill_id", "knowledge_chunks", ["skill_id"])
    # Retrieval is always hard-filtered by skill, then ranked. This composite
    # index serves the filter without an extra sort over the whole table.
    op.create_index(
        "ix_knowledge_chunks_skill_version",
        "knowledge_chunks",
        ["skill_id", "exercise_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_skill_version", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_skill_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_exercise_version_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
