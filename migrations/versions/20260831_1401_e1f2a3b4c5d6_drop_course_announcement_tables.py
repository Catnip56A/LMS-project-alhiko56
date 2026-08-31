"""Drop course_announcement/course_announcement_reply — data migrated to forum_message

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-31 14:01:00.000000

Part 2 of 2 (see d0e1f2a3b4c5 for the schema+data migration this depends on). Every
CourseAnnouncement/CourseAnnouncementReply row was copied into a ForumMessage in that
course's new course-scoped ForumChannel by the previous migration; the Announcements tab now
reads from there instead. This migration only drops the now-superseded source tables — it does
not move any more data.

Destructive: drops both tables outright, same discipline as c9d0e1f2a3b4 (the PDFDocument
removal). Not safe to run against a database whose migrated data in d0e1f2a3b4c5 hasn't been
spot-checked against these tables first — once this runs, the originals are gone.
downgrade() restores the empty schema only, not any data.
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('course_announcement_reply')
    op.drop_table('course_announcement')


def downgrade():
    op.create_table(
        'course_announcement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['user.id']),
        sa.ForeignKeyConstraint(['course_id'], ['course.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'course_announcement_reply',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('announcement_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('parent_reply_id', sa.Integer(), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['announcement_id'], ['course_announcement.id']),
        sa.ForeignKeyConstraint(['parent_reply_id'], ['course_announcement_reply.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
