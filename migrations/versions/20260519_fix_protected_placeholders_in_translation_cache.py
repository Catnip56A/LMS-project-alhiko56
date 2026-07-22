"""Fix broken {PROTECTED N} placeholders in translation cache tables

Revision ID: 20260519_fix_protected_placeholders
Revises: 20260518_1506_fix_content_view_content_id_type
Create Date: 2026-05-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e5c4a2b1f039'
down_revision = 'c3a1b2d40518'
branch_labels = None
depends_on = None

# Matches {PROTECTED 0}, {PROTECTED_0}, {PROTECTED 1}, {PROTECTED_1}, etc.
_PATTERN = r'\{PROTECTED[_ ]\d+\}'
_REPLACEMENT = 'Yonca'


def _fix_table(table_name: str) -> None:
    t = sa.table(table_name, sa.column('translated_text', sa.Text()))
    op.get_bind().execute(
        sa.update(t)
        .where(t.c.translated_text.op('~')(_PATTERN))
        .values(
            translated_text=sa.func.regexp_replace(
                t.c.translated_text, _PATTERN, _REPLACEMENT, 'g'
            )
        )
    )


def upgrade():
    _fix_table('translation')
    _fix_table('content_translation')


def downgrade():
    pass
