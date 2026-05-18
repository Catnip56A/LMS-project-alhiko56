"""Add ContentView model for tracking content viewing time

Revision ID: 8a9b0c1d2e3f
Revises: 63af7e9b99c4
Create Date: 2026-05-16 17:12:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8a9b0c1d2e3f'
down_revision = '63af7e9b99c4'
branch_labels = None
depends_on = None


def upgrade():
    # Create the content_view table
    op.create_table('content_view',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('content_type', sa.String(length=50), nullable=False),
    sa.Column('content_id', sa.Integer(), nullable=False),
    sa.Column('viewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('viewing_duration', sa.Integer(), server_default='0', nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('content_view_user_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('content_view_pkey'))
    )


def downgrade():
    # Drop the content_view table
    op.drop_table('content_view')
