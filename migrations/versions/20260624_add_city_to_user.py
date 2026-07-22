"""Add city column to user

Revision ID: 20260624_add_city_to_user
Revises: 20260623_admin_permissions
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = '20260624_add_city_to_user'
down_revision = '20260623_admin_permissions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('city', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('user', 'city')
