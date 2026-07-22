"""Remove unused About Features section columns from HomeContent

Revision ID: b8f6c2e3a051
Revises: a7d3e1c8f042
Create Date: 2026-05-24 09:05:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b8f6c2e3a051'
down_revision = 'a7d3e1c8f042'
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
