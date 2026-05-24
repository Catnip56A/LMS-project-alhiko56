"""Add second gallery fields to about_company

Revision ID: 20260524_add_about_gallery_2_fields
Revises: 20260519_fix_protected_placeholders
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '20260524_add_about_gallery_2_fields'
down_revision = '20260519_fix_protected_placeholders'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('home_content', schema=None) as batch_op:
        batch_op.add_column(sa.Column('about_gallery_2_images', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('about_gallery_2_title', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('about_gallery_2_subtitle', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('home_content', schema=None) as batch_op:
        batch_op.drop_column('about_gallery_2_subtitle')
        batch_op.drop_column('about_gallery_2_title')
        batch_op.drop_column('about_gallery_2_images')
