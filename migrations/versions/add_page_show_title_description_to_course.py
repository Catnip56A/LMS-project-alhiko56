"""Add page_show_title and page_show_description to Course

Revision ID: 9c7a1b3e2f5d
Revises: 20260519_fix_protected_placeholders_in_translation_cache
Create Date: 2026-05-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c7a1b3e2f5d'
down_revision = 'e5c4a2b1f039'
branch_labels = None
depends_on = None


def upgrade():
    # Columns already added by c2f4b6a8d9e1 (add_page_visibility_toggles) — no-op
    pass


def downgrade():
    pass
