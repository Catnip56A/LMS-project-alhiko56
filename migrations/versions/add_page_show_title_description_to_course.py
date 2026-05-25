"""Add page_show_title and page_show_description to Course

Revision ID: 9c7a1b3e2f5d
Revises: 20260519_fix_protected_placeholders_in_translation_cache
Create Date: 2026-05-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c7a1b3e2f5d'
down_revision = 'e5c4a2b1f039'
branch_labels = None
depends_on = None


def upgrade():
    # Add page_show_title and page_show_description columns to course table
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.add_column(sa.Column('page_show_title', sa.Boolean(), nullable=True, server_default='1'))
        batch_op.add_column(sa.Column('page_show_description', sa.Boolean(), nullable=True, server_default='1'))

    # Set NOT NULL after data is populated
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.alter_column('page_show_title', existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column('page_show_description', existing_type=sa.Boolean(), nullable=False)


def downgrade():
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.drop_column('page_show_description')
        batch_op.drop_column('page_show_title')
