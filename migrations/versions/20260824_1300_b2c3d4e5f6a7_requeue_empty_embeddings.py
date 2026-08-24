"""Re-queue content that indexed to zero chunks, so improved extraction can retry it

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-24 13:00:00.000000

`embedded_at` is the sweep's "already handled" marker, so anything that produced zero
chunks stays permanently unindexed even after the extraction bug that caused it is fixed.
Two such bugs have now been fixed (title-based file-type guessing, and lectures stored as
content_type='file' never reaching transcription), so clear the marker for rows that have
no embeddings and let the sweep try again with the current code.

Genuinely unextractable items (images, archives) simply re-fail once and are re-marked.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

course_content = sa.table(
    'course_content',
    sa.column('id', sa.Integer),
    sa.column('embedded_at', sa.DateTime),
)
content_embedding = sa.table(
    'content_embedding',
    sa.column('course_content_id', sa.Integer),
)


def upgrade():
    conn = op.get_bind()
    has_chunks = sa.select(content_embedding.c.course_content_id).where(
        content_embedding.c.course_content_id == course_content.c.id
    )
    result = conn.execute(
        sa.update(course_content)
        .where(course_content.c.embedded_at.isnot(None))
        .where(~sa.exists(has_chunks))
        .values(embedded_at=None)
    )
    print(f"Re-queued {result.rowcount} content item(s) that had indexed to zero chunks")


def downgrade():
    # One-way by design: embedded_at is a processing marker, not user data, and the original
    # per-row timestamps are not recoverable. The sweep re-populates it on the next pass.
    pass
