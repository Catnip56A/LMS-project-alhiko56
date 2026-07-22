"""Add admin_permissions column to user

Revision ID: 20260623_admin_permissions
Revises: 20260620_certificates
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = '20260623_admin_permissions'
down_revision = '20260620_certificates'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('admin_permissions', sa.JSON(), nullable=True))
    # Existing is_admin=True users keep NULL admin_permissions, which means full access.
    # Explicitly ensure no partial-permission row was somehow pre-set for them.
    op.get_bind().execute(
        sa.text('UPDATE "user" SET admin_permissions = NULL WHERE is_admin = TRUE')
    )


def downgrade():
    op.drop_column('user', 'admin_permissions')
