"""Add first_name/last_name to User and create certificates table

Revision ID: 20260620_certificates
Revises: 20260615_content_view_fk_cascade
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260620_certificates'
down_revision = '20260615_content_view_fk_cascade'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('user', sa.Column('last_name', sa.String(100), nullable=True))

    op.create_table(
        'certificates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id'), nullable=False),
        sa.Column('course_id', sa.Integer, sa.ForeignKey('course.id'), nullable=False),
        sa.Column('issued_by', sa.Integer, sa.ForeignKey('user.id'), nullable=False),
        sa.Column('issued_at', sa.DateTime, nullable=False),
        sa.Column('revoked', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('revoked_by', sa.Integer, sa.ForeignKey('user.id'), nullable=True),
        sa.Column('revoked_at', sa.DateTime, nullable=True),
        sa.Column('student_name', sa.String(200), nullable=False),
    )


def downgrade():
    op.drop_table('certificates')
    op.drop_column('user', 'last_name')
    op.drop_column('user', 'first_name')
