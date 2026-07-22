"""Drop legacy tab label fields from course

Revision ID: drop_legacy_tab_labels
Revises: b9b29e2f764f
Create Date: 2026-03-17 00:28:00
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1c3e5f7b2d4'
down_revision = 'b9b29e2f764f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.drop_column('tab_content_label')
        batch_op.drop_column('tab_announcements_label')
        batch_op.drop_column('tab_reviews_label')
        batch_op.drop_column('tab_assignments_label')


def downgrade():
    with op.batch_alter_table('course', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tab_assignments_label', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('tab_reviews_label', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('tab_announcements_label', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('tab_content_label', sa.String(50), nullable=True))
