"""Add r2_key/file_mime_type to course_content, for Cloudflare R2-backed storage

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-27 11:06:00.000000

Nullable, additive-only: NULL r2_key means bytes haven't been migrated off Drive yet
(drive_file_id stays the fallback, see lms/routes/api.py's _content_media_url), NULL
file_mime_type means the row predates content-type sniffing and the title-extension
guess is still used. No data is moved by this migration — the one-time Drive-to-R2
backfill is a separate script (scripts/migration/backfill_drive_to_r2.py), not an
Alembic data migration, since it does bulk network I/O rather than a DB-internal
transform and needs to be resumable/rate-limited in a way `flask db upgrade` isn't.
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('course_content', schema=None) as batch_op:
        batch_op.add_column(sa.Column('r2_key', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('file_mime_type', sa.String(length=150), nullable=True))


def downgrade():
    with op.batch_alter_table('course_content', schema=None) as batch_op:
        batch_op.drop_column('file_mime_type')
        batch_op.drop_column('r2_key')
