"""Remove unused About Features section columns from HomeContent

Revision ID: remove_about_features_20260524
Revises: 20260524_add_about_gallery_2_fields
Create Date: 2026-05-24 09:05:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'remove_about_features_20260524'
down_revision = '20260524_add_about_gallery_2_fields'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('home_content', schema=None) as batch_op:
        batch_op.drop_column('about_features')
        batch_op.drop_column('about_features_title')
        batch_op.drop_column('about_features_subtitle')


def downgrade():
    with op.batch_alter_table('home_content', schema=None) as batch_op:
        batch_op.add_column(sa.Column('about_features', postgresql.JSON(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column('about_features_subtitle', sa.VARCHAR(length=500), nullable=True))
        batch_op.add_column(sa.Column('about_features_title', sa.VARCHAR(length=200), nullable=True))
