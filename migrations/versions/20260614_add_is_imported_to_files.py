"""Add is_imported column to Resource, PDFDocument, CourseContent

Revision ID: 20260614_is_imported
Revises: 20260527_1055_create_page_limitation
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260614_is_imported'
down_revision = 'create_page_limitation'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('resource', sa.Column('is_imported', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('pdf_document', sa.Column('is_imported', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('course_content', sa.Column('is_imported', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('resource', 'is_imported')
    op.drop_column('pdf_document', 'is_imported')
    op.drop_column('course_content', 'is_imported')
