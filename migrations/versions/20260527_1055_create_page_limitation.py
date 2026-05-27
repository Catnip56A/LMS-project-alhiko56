"""Create page_limitation table

Revision ID: create_page_limitation
Revises: add_declined_field
Create Date: 2026-05-27 10:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'create_page_limitation'
down_revision = 'add_declined_field'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'page_limitation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_key', sa.String(length=50), nullable=False),
        sa.Column('page_name', sa.String(length=100), nullable=False),
        sa.Column('is_limited', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('page_key')
    )


def downgrade():
    op.drop_table('page_limitation')
