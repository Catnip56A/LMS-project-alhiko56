"""Add is_downloadable to CourseContent

Revision ID: 20260626_content_downloadable
Revises: 20260624_add_created_at_to_user
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = '20260626_content_downloadable'
down_revision = '20260624_add_created_at_to_user'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('course_content', sa.Column('is_downloadable', sa.Boolean(), nullable=True, server_default=sa.false()))


def downgrade():
    op.drop_column('course_content', 'is_downloadable')
