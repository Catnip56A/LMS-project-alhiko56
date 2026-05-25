"""Add about_gallery_2_* columns to HomeContent

Revision ID: a7d3e1c8f042
Revises: add_page_show_title_description_to_course
Create Date: 2026-05-24

"""
from alembic import op
import sqlalchemy as sa

revision = 'a7d3e1c8f042'
down_revision = '9c7a1b3e2f5d'
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
