"""Remove MoxoTest feature: drop tavi_test table and purge its references

Revision ID: a1b2c3d4e5f6
Revises: b6028c3baa00
Create Date: 2026-08-24 12:00:00.000000

The MOXO Test page was a "coming soon" stub with no data (tavi_test was empty at
removal time). Dropping the table, plus the two places its references were persisted
in existing rows: the SiteSettings navigation menu and any sub-admin's permission list.
Column defaults alone only affect new rows, hence the data migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = 'b6028c3baa00'
branch_labels = None
depends_on = None

# Minimal table definitions for the data migration (avoid importing app models).
site_settings = sa.table(
    'site_settings',
    sa.column('id', sa.Integer),
    sa.column('navigation_items', postgresql.JSON),
)
user_table = sa.table(
    'user',
    sa.column('id', sa.Integer),
    sa.column('admin_permissions', postgresql.JSON),
)

_MOXO_NAV = {"name": "MOXO Test", "url": "/#moxo", "active": True}
_MOXO_PERM = 'moxo_test_management'


def upgrade():
    conn = op.get_bind()

    # 1. Strip the MOXO nav entry from existing SiteSettings rows.
    for row_id, items in conn.execute(sa.select(site_settings.c.id, site_settings.c.navigation_items)):
        if not items:
            continue
        cleaned = [i for i in items if not (isinstance(i, dict) and i.get('url') == '/#moxo')]
        if len(cleaned) != len(items):
            conn.execute(
                sa.update(site_settings).where(site_settings.c.id == row_id).values(navigation_items=cleaned)
            )

    # 2. Strip the permission key from any sub-admin's permission list.
    for row_id, perms in conn.execute(sa.select(user_table.c.id, user_table.c.admin_permissions)):
        if not perms:
            continue
        cleaned = [p for p in perms if p != _MOXO_PERM]
        if len(cleaned) != len(perms):
            conn.execute(
                sa.update(user_table).where(user_table.c.id == row_id).values(admin_permissions=cleaned)
            )

    # 3. Drop the (empty) table itself.
    op.drop_table('tavi_test')


def downgrade():
    op.create_table(
        'tavi_test',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    conn = op.get_bind()
    for row_id, items in conn.execute(sa.select(site_settings.c.id, site_settings.c.navigation_items)):
        if not items or any(isinstance(i, dict) and i.get('url') == '/#moxo' for i in items):
            continue
        restored = list(items)
        # Reinsert in its original position (before the About entry) when possible.
        idx = next((n for n, i in enumerate(restored)
                    if isinstance(i, dict) and i.get('url') == '/#about'), len(restored))
        restored.insert(idx, dict(_MOXO_NAV))
        conn.execute(
            sa.update(site_settings).where(site_settings.c.id == row_id).values(navigation_items=restored)
        )
