"""Add r2_preview_key to course_content, for converted-PDF Office document previews

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-27 12:20:00.000000

Nullable, additive-only. Browsers have no native renderer for Office formats
(.doc/.docx/.ppt/.pptx/.xls/.xlsx) the way they do for PDF/images — Google Drive's own
/preview endpoint used to handle this by converting the file server-side before returning it,
which raw R2 bytes have no equivalent for. r2_preview_key holds the R2 key of a
headless-LibreOffice-converted PDF (see lms/office_preview.py), generated at ingestion time
(upload, Picker import, or the Drive-to-R2 backfill) and used only for in-browser viewing —
downloads and RAG extraction still use the original file at r2_key. NULL means either the
original is already natively viewable (PDF/image/video/audio) or the row predates this feature.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('course_content', schema=None) as batch_op:
        batch_op.add_column(sa.Column('r2_preview_key', sa.String(length=512), nullable=True))


def downgrade():
    with op.batch_alter_table('course_content', schema=None) as batch_op:
        batch_op.drop_column('r2_preview_key')
