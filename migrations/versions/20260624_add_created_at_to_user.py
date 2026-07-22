"""Add created_at column to user

Revision ID: 20260624_add_created_at_to_user
Revises: 20260624_add_city_to_user
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = '20260624_add_created_at_to_user'
down_revision = '20260624_add_city_to_user'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()))


def downgrade():
    op.drop_column('user', 'created_at')
