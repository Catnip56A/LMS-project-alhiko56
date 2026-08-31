"""Add transcript_segment table and course_content.transcript_language, for subtitles

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-28 08:02:00.000000

Nullable/additive. transcript_segment persists the raw, fine-grained (~2-8s) Whisper
segments a video/audio CourseContent produces — separately from the much coarser ~45s
windows ContentEmbedding stores for RAG retrieval, which are too coarse for subtitle cues.
Populated as a side effect of transcription in rag_service.embed_content_item (see
lms/subtitle_service.py); NULL/empty for content never transcribed, non-video/audio content,
or content transcribed before this migration (see scripts/migration/
backfill_transcript_segments.py for backfilling those). transcript_language is Whisper's own
detected language code (e.g. 'en'/'ru'), used to label the subtitle track correctly.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'transcript_segment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_content_id', sa.Integer(), nullable=False),
        sa.Column('segment_index', sa.Integer(), nullable=False),
        sa.Column('start_seconds', sa.Float(), nullable=False),
        sa.Column('end_seconds', sa.Float(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['course_content_id'], ['course_content.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_content_id', 'segment_index', name='uq_transcript_segment_index'),
    )
    with op.batch_alter_table('course_content', schema=None) as batch_op:
        batch_op.add_column(sa.Column('transcript_language', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('course_content', schema=None) as batch_op:
        batch_op.drop_column('transcript_language')

    op.drop_table('transcript_segment')
