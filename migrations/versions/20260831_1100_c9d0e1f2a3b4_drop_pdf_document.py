"""Drop pdf_document — feature removed (no reachable UI, explicit decision to remove)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-31 11:00:00.000000

PDFDocument (a PIN-gated PDF sharing feature, separate from CourseContent) turned out to have
zero reachable UI anywhere in the app — its only frontend was markup inside index.html, and
index.html has been rendered by zero routes since the MoxoTest route removal earlier this
session (confirmed via a repo-wide grep for render_template('index.html'). Found while
migrating it to R2 alongside CourseAssignmentSubmission (previous migration, b8c9d0e1f2a3);
initially migrated-and-kept per an explicit decision, then the user asked for it to be fully
removed once they understood it was genuinely unreachable rather than just missing a page.

Destructive: drops the table outright, not a nullable/additive change like the rest of this
migration chain. At the time of writing, the dev database's pdf_document table was empty (the
feature had no UI to create rows through since before this session started), so no real data
loss occurred here — but this migration is not safe to run against a database with real rows
in that table without exporting them first, since downgrade() only restores the empty schema,
not any data.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('pdf_document')


def downgrade():
    op.create_table(
        'pdf_document',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('filename', sa.String(length=300), nullable=False),
        sa.Column('original_filename', sa.String(length=300), nullable=False),
        sa.Column('drive_file_id', sa.String(length=100), nullable=True),
        sa.Column('drive_view_link', sa.String(length=300), nullable=True),
        sa.Column('r2_key', sa.String(length=500), nullable=True),
        sa.Column('file_mime_type', sa.String(length=150), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('access_pin', sa.String(length=10), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('upload_date', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('allow_others_to_view', sa.Boolean(), nullable=True),
        sa.Column('is_imported', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['uploaded_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
