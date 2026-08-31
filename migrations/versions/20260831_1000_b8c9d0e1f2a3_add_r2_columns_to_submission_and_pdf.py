"""Add R2 storage columns to course_assignment_submission and pdf_document

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-31 10:00:00.000000

Nullable/additive, same shape as course_content's r2_key/r2_preview_key/file_mime_type
(migration d4e5f6a7b8c9/e5f6a7b8c9d0). Extends the Cloudflare R2 migration to the two
remaining Drive-backed document models: CourseAssignmentSubmission (assignment uploads) and
PDFDocument (the PIN-gated PDF sharing feature). drive_file_id/drive_view_link are kept on
both — provenance only once r2_key is set, same convention as course_content. pdf_document has
no preview-key column since it's PDF-only by construction (see upload_pdf's
expected_mimes=PDF_MIME_TYPES) and never needs the Office-to-PDF conversion course_content and
submissions do.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('course_assignment_submission', schema=None) as batch_op:
        batch_op.add_column(sa.Column('r2_key', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('r2_preview_key', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('file_mime_type', sa.String(length=150), nullable=True))

    with op.batch_alter_table('pdf_document', schema=None) as batch_op:
        batch_op.add_column(sa.Column('r2_key', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('file_mime_type', sa.String(length=150), nullable=True))


def downgrade():
    with op.batch_alter_table('pdf_document', schema=None) as batch_op:
        batch_op.drop_column('file_mime_type')
        batch_op.drop_column('r2_key')

    with op.batch_alter_table('course_assignment_submission', schema=None) as batch_op:
        batch_op.drop_column('file_mime_type')
        batch_op.drop_column('r2_preview_key')
        batch_op.drop_column('r2_key')
