"""Add video_moment_flag/video_moment tables and enrollment.moment_flags_blocked

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-28 07:03:00.000000

Video moment highlighting (Phase 6 addendum): two new tables plus one new column, all
additive. video_moment_flag is an append-only signal log (one row per automatic
keyword-trigger hit or student click); video_moment is the low-volume, mutable, promoted
artifact (weight, status, caption) created once a flag bucket crosses its course's adaptive
weighting threshold — see lms/moment_service.py for why these are kept separate rather than
one table. enrollment.moment_flags_blocked (default false) is a per-course teacher-set
moderation flag, mirroring the existing enrollment.is_teacher column's per-(user,course)
scope rather than a new moderation table.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'video_moment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_content_id', sa.Integer(), nullable=False),
        sa.Column('bucket_index', sa.Integer(), nullable=False),
        sa.Column('timestamp_seconds', sa.Float(), nullable=False),
        sa.Column('weight_at_promotion', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('frame_phash', sa.String(length=32), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('captioned_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['course_content_id'], ['course_content.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_content_id', 'bucket_index', name='uq_video_moment_bucket'),
    )
    op.create_table(
        'video_moment_flag',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_content_id', sa.Integer(), nullable=False),
        sa.Column('timestamp_seconds', sa.Float(), nullable=False),
        sa.Column('bucket_index', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('added_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['added_by'], ['user.id']),
        sa.ForeignKeyConstraint(['course_content_id'], ['course_content.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_content_id', 'bucket_index', 'added_by', name='uq_video_moment_flag_bucket_user'),
    )
    with op.batch_alter_table('video_moment_flag', schema=None) as batch_op:
        batch_op.create_index('idx_video_moment_flag_bucket', ['course_content_id', 'bucket_index'], unique=False)

    with op.batch_alter_table('enrollment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('moment_flags_blocked', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade():
    with op.batch_alter_table('enrollment', schema=None) as batch_op:
        batch_op.drop_column('moment_flags_blocked')

    with op.batch_alter_table('video_moment_flag', schema=None) as batch_op:
        batch_op.drop_index('idx_video_moment_flag_bucket')

    op.drop_table('video_moment_flag')
    op.drop_table('video_moment')
