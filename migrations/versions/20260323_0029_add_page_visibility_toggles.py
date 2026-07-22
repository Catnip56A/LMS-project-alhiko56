"""Add page visibility toggles to course

Revision ID: c2f4b6a8d9e1
Revises: a1c3e5f7b2d4
Create Date: 2026-03-23 00:29:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2f4b6a8d9e1'
down_revision = 'a1c3e5f7b2d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.add_column(sa.Column('page_show_title', sa.Boolean(), server_default='true', nullable=False))
        batch_op.add_column(sa.Column('page_show_description', sa.Boolean(), server_default='true', nullable=False))


def downgrade():
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.drop_column('page_show_description')
        batch_op.drop_column('page_show_title')
