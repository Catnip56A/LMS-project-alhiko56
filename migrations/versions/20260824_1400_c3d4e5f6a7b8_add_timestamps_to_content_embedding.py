"""Add start_seconds/end_seconds to content_embedding, for timestamped video moments

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-24 14:00:00.000000

Nullable, additive-only: plain text/PDF/DOCX/PPTX chunks have no time axis and stay NULL.
Only chunks produced from a timestamped video/audio transcript (see
rag_service.chunk_segments_by_time) populate these, letting Ask AI citations eventually
point at a moment in a video rather than just the file (Phase 6 addendum, step 2).
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('content_embedding', schema=None) as batch_op:
        batch_op.add_column(sa.Column('start_seconds', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('end_seconds', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('content_embedding', schema=None) as batch_op:
        batch_op.drop_column('end_seconds')
        batch_op.drop_column('start_seconds')
