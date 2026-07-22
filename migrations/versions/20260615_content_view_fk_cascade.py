"""Add ON DELETE CASCADE to content_view.user_id FK

Revision ID: 20260615_content_view_fk_cascade
Revises: 20260614_add_is_imported_to_files
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision = '20260615_content_view_fk_cascade'
down_revision = '20260614_is_imported'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('content_view', schema=None) as batch_op:
        batch_op.drop_constraint('content_view_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'content_view_user_id_fkey',
            'user',
            ['user_id'],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade():
    with op.batch_alter_table('content_view', schema=None) as batch_op:
        batch_op.drop_constraint('content_view_user_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'content_view_user_id_fkey',
            'user',
            ['user_id'],
            ['id']
        )
