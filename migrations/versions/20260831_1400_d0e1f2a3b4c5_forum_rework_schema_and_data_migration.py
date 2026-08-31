"""Forum rework: course/group/dm channel support, pin/soft-delete, migrate CourseAnnouncement data

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-31 14:00:00.000000

Part 1 of 2 (see e1f2a3b4c5d6 for the destructive second half — dropping
course_announcement/course_announcement_reply once this migration's data move is verified).

Unifies global channels, course-scoped channels (replacing CourseAnnouncement/
CourseAnnouncementReply), moderator-created Groups, and private 1:1 DMs onto the same
ForumChannel/ForumMessage pair, distinguished by a new channel_type column — see
lms/forum_service.py and the "Forum rework" plan for the full design.

Schema changes, all nullable/additive except channel_type (has a default) and
forum_message.channel_id (NOT NULL, but every existing row gets backfilled in this same
migration before the NOT NULL constraint would matter — see the data-migration block):
  - forum_channel: channel_type, course_id, created_by, membership_mode, retention_days
  - forum_channel_membership: new table (dm participants, invite-only group members)
  - forum_message: channel_id (replaces the old bare-string `channel` column — no FK existed
    between ForumMessage.channel and ForumChannel.slug before this, a real pre-existing gap),
    pinned, deleted_at; parent_id's FK gains ondelete='CASCADE' (deleting a message now
    deliberately takes its replies with it — matters for the hard-delete expiry sweep and
    moderator "clear history" action; single-message deletion is a soft delete instead,
    specifically so that action never triggers this cascade)

Data migration (this file, not a separate backfill script — real existing announcement data,
unlike the empty PDFDocument table dropped in c9d0e1f2a3b4):
  1. One ForumChannel (channel_type='course', slug=f'course-{id}') created for every existing
     Course.
  2. Every existing ForumMessage.channel string value resolved to its matching
     ForumChannel.slug's id for the new channel_id column.
  3. Every CourseAnnouncement becomes a ForumMessage in that course's new channel — the title
     has no ForumMessage equivalent, so it's folded into the message body as a bold-prefixed
     first line rather than adding a title column nothing else needs.
  4. Every CourseAnnouncementReply becomes a child ForumMessage (parent_id preserved,
     re-mapped from the old self-referential reply-id space to the new message-id space).

course_announcement/course_announcement_reply are left in place after this migration —
dropping them is the deliberately separate, explicitly destructive second migration
(e1f2a3b4c5d6), so there's a real checkpoint to verify the migrated data against the
originals before the source tables are gone for good.
"""
from alembic import op
import sqlalchemy as sa

revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # --- schema ---
    with op.batch_alter_table('forum_channel', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel_type', sa.String(length=20), nullable=False, server_default='global'))
        batch_op.add_column(sa.Column('course_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('membership_mode', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('retention_days', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_forum_channel_course_id', 'course', ['course_id'], ['id'])
        batch_op.create_foreign_key('fk_forum_channel_created_by', 'user', ['created_by'], ['id'])

    op.create_table(
        'forum_channel_membership',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['forum_channel.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel_id', 'user_id', name='uq_forum_channel_membership'),
    )

    with op.batch_alter_table('forum_message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel_id', sa.Integer(), nullable=True))  # NOT NULL enforced below, after backfill
        batch_op.add_column(sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.text('false')))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))

    # --- data migration ---
    forum_channel = sa.table(
        'forum_channel',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('slug', sa.String),
        sa.column('channel_type', sa.String),
        sa.column('course_id', sa.Integer),
        sa.column('requires_login', sa.Boolean),
        sa.column('is_active', sa.Boolean),
    )
    forum_message = sa.table(
        'forum_message',
        sa.column('id', sa.Integer),
        sa.column('user_id', sa.Integer),
        sa.column('username', sa.String),
        sa.column('message', sa.Text),
        sa.column('timestamp', sa.DateTime),
        sa.column('parent_id', sa.Integer),
        sa.column('channel', sa.String),
        sa.column('channel_id', sa.Integer),
    )
    course = sa.table('course', sa.column('id', sa.Integer), sa.column('title', sa.String))
    course_announcement = sa.table(
        'course_announcement',
        sa.column('id', sa.Integer),
        sa.column('course_id', sa.Integer),
        sa.column('title', sa.String),
        sa.column('message', sa.Text),
        sa.column('author_id', sa.Integer),
        sa.column('created_at', sa.DateTime),
    )
    course_announcement_reply = sa.table(
        'course_announcement_reply',
        sa.column('id', sa.Integer),
        sa.column('announcement_id', sa.Integer),
        sa.column('user_id', sa.Integer),
        sa.column('parent_reply_id', sa.Integer),
        sa.column('message', sa.Text),
        sa.column('created_at', sa.DateTime),
    )

    # 1. One course channel per existing course.
    course_channel_id = {}  # course_id -> new forum_channel.id
    for course_id, title in conn.execute(sa.select(course.c.id, course.c.title)):
        slug = f'course-{course_id}'
        new_id = conn.execute(
            sa.insert(forum_channel).values(
                name=title, slug=slug, channel_type='course', course_id=course_id,
                requires_login=True, is_active=True,
            ).returning(forum_channel.c.id)
        ).scalar_one()
        course_channel_id[course_id] = new_id

    # 2. Backfill channel_id on every existing forum_message from its old channel-slug string.
    slug_to_id = {
        slug: cid for cid, slug in conn.execute(sa.select(forum_channel.c.id, forum_channel.c.slug))
    }
    for old_slug in {row[0] for row in conn.execute(sa.select(forum_message.c.channel).distinct())}:
        target_id = slug_to_id.get(old_slug)
        if target_id is None:
            # Orphaned channel string with no matching ForumChannel row (shouldn't normally
            # happen — channel was never FK-enforced before this migration) — create one
            # rather than dropping messages on the floor.
            target_id = conn.execute(
                sa.insert(forum_channel).values(
                    name=old_slug, slug=old_slug, channel_type='global',
                    requires_login=False, is_active=True,
                ).returning(forum_channel.c.id)
            ).scalar_one()
            slug_to_id[old_slug] = target_id
        conn.execute(
            sa.update(forum_message).where(forum_message.c.channel == old_slug).values(channel_id=target_id)
        )

    # 3 & 4. Migrate CourseAnnouncement (+ its replies) into ForumMessage rows in the new
    # course channel, title folded into the message body, reply parent-chain preserved
    # (remapped from the old course_announcement_reply id-space to the new forum_message
    # id-space).
    reply_to_new_message_id = {}  # old course_announcement_reply.id -> new forum_message.id
    for ann_id, ann_course_id, title, message, author_id, created_at in conn.execute(
        sa.select(
            course_announcement.c.id, course_announcement.c.course_id, course_announcement.c.title,
            course_announcement.c.message, course_announcement.c.author_id, course_announcement.c.created_at,
        )
    ):
        channel_id = course_channel_id.get(ann_course_id)
        if channel_id is None:
            continue  # announcement references a course row that no longer exists
        top_message_id = conn.execute(
            sa.insert(forum_message).values(
                user_id=author_id, username=None, message=f'**{title}**\n\n{message}',
                timestamp=created_at, parent_id=None, channel_id=channel_id,
            ).returning(forum_message.c.id)
        ).scalar_one()

        # Replies for this announcement, oldest first so a reply-to-a-reply's parent has
        # already been migrated (and is therefore in reply_to_new_message_id) by the time we
        # get to it.
        for reply_id, reply_user_id, parent_reply_id, reply_message, reply_created_at in conn.execute(
            sa.select(
                course_announcement_reply.c.id, course_announcement_reply.c.user_id,
                course_announcement_reply.c.parent_reply_id, course_announcement_reply.c.message,
                course_announcement_reply.c.created_at,
            )
            .where(course_announcement_reply.c.announcement_id == ann_id)
            .order_by(course_announcement_reply.c.id)
        ):
            new_parent_id = reply_to_new_message_id.get(parent_reply_id, top_message_id)
            new_reply_id = conn.execute(
                sa.insert(forum_message).values(
                    user_id=reply_user_id, username=None, message=reply_message,
                    timestamp=reply_created_at, parent_id=new_parent_id, channel_id=channel_id,
                ).returning(forum_message.c.id)
            ).scalar_one()
            reply_to_new_message_id[reply_id] = new_reply_id

    # --- finalize schema now that every row has a channel_id ---
    with op.batch_alter_table('forum_message', schema=None) as batch_op:
        batch_op.alter_column('channel_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('channel')
        batch_op.create_foreign_key('fk_forum_message_channel_id', 'forum_channel', ['channel_id'], ['id'])
        batch_op.drop_constraint('forum_message_parent_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'forum_message_parent_id_fkey', 'forum_message', ['parent_id'], ['id'], ondelete='CASCADE'
        )


def downgrade():
    # One-way by design for the data-migration half (announcement titles/reply-nesting are
    # not cleanly recoverable from the merged ForumMessage rows). Schema-only revert:
    with op.batch_alter_table('forum_message', schema=None) as batch_op:
        batch_op.drop_constraint('forum_message_parent_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key('forum_message_parent_id_fkey', 'forum_message', ['parent_id'], ['id'])
        batch_op.add_column(sa.Column('channel', sa.String(length=50), nullable=False, server_default='general'))
        batch_op.drop_constraint('fk_forum_message_channel_id', type_='foreignkey')
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('pinned')
        batch_op.drop_column('channel_id')

    op.drop_table('forum_channel_membership')

    with op.batch_alter_table('forum_channel', schema=None) as batch_op:
        batch_op.drop_constraint('fk_forum_channel_created_by', type_='foreignkey')
        batch_op.drop_constraint('fk_forum_channel_course_id', type_='foreignkey')
        batch_op.drop_column('retention_days')
        batch_op.drop_column('membership_mode')
        batch_op.drop_column('created_by')
        batch_op.drop_column('course_id')
        batch_op.drop_column('channel_type')
