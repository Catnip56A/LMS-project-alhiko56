"""
Forum service — runtime layer (Flask/DB-aware), mirrors moment_service.py's/subtitle_service.py's
role. Covers the unified forum system: global channels (the original use of ForumChannel/
ForumMessage), course-scoped channels (replacing the old CourseAnnouncement/
CourseAnnouncementReply pair), moderator-created Groups, and private 1:1 DMs — all the same
two tables, distinguished by ForumChannel.channel_type. See the "Forum rework" plan for the
full design.
"""
from datetime import datetime, timedelta
import logging

from lms.models import db, ForumChannel, ForumMessage, ForumChannelMembership

logger = logging.getLogger(__name__)

# Deliberately tighter than the site-wide MAX_CONTENT_LENGTH (500MB) — a chat attachment is a
# quick sync upload inline in a request handler (see CLAUDE.md's async-conversion rule), not
# something that should hold a gunicorn worker for a large-file transfer.
FORUM_ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024


def ensure_course_channel(course):
    """Get-or-create the course-scoped channel for `course`. Called right after a Course row
    is created; also safe to call again for a pre-existing course that doesn't have one yet
    (get-or-create, idempotent)."""
    channel = ForumChannel.query.filter_by(channel_type='course', course_id=course.id).first()
    if channel:
        return channel
    channel = ForumChannel(
        name=course.title,
        slug=f'course-{course.id}',
        channel_type='course',
        course_id=course.id,
        requires_login=True,
        is_active=True,
    )
    db.session.add(channel)
    db.session.commit()
    return channel


def is_member(channel, user) -> bool:
    if not (user and getattr(user, 'is_authenticated', False)):
        return False
    return ForumChannelMembership.query.filter_by(channel_id=channel.id, user_id=user.id).first() is not None


def can_view_channel(channel, user) -> bool:
    """Whether `user` (may be None/anonymous) can view this channel's messages."""
    if channel.channel_type == 'course':
        course = channel.course
        if not course or not (user and getattr(user, 'is_authenticated', False)):
            return False
        return course.is_managed_by(user) or user in course.users
    if channel.channel_type == 'dm':
        return is_member(channel, user)
    if channel.channel_type == 'group' and channel.membership_mode == 'invite_only':
        return is_member(channel, user)
    # global channel, or an 'open' group — same existing access gates
    if channel.admin_only:
        return bool(user and getattr(user, 'is_authenticated', False) and user.is_admin)
    if channel.requires_login:
        return bool(user and getattr(user, 'is_authenticated', False))
    return True


def can_post_to_channel(channel, user) -> bool:
    """Posting has the same gate as viewing for every channel type in this app today —
    kept as its own function so a future divergence (e.g. read-only announcement channels)
    doesn't require touching every call site."""
    return can_view_channel(channel, user)


def can_moderate_channel(channel, user) -> bool:
    """Whether `user` can pin/soft-delete-others'-messages/clear-history in this channel."""
    if not (user and getattr(user, 'is_authenticated', False)):
        return False
    if channel.channel_type == 'course':
        return bool(channel.course and channel.course.is_managed_by(user))
    if channel.channel_type == 'dm':
        return False  # no moderator role in a private conversation
    # global or group channel
    return user.has_perm('forum_management') or channel.created_by == user.id


def find_or_create_dm(user_a, user_b):
    """Deterministic, idempotent lookup — same DM channel regardless of argument order."""
    lo, hi = sorted([user_a.id, user_b.id])
    slug = f'dm-{lo}-{hi}'
    channel = ForumChannel.query.filter_by(slug=slug).first()
    if channel:
        return channel
    channel = ForumChannel(
        name=f'DM {lo}-{hi}',
        slug=slug,
        channel_type='dm',
        requires_login=True,
        is_active=True,
    )
    db.session.add(channel)
    db.session.flush()
    db.session.add(ForumChannelMembership(channel_id=channel.id, user_id=lo))
    db.session.add(ForumChannelMembership(channel_id=channel.id, user_id=hi))
    db.session.commit()
    return channel


def purge_expired_channel_messages() -> dict:
    """Hard-delete messages older than each channel's own retention_days, if set — the
    time-based auto-expiry sweep (see job_manager.run_scheduled_forum_purge). Replies cascade
    automatically at the DB level (ForumMessage.parent_id has ondelete='CASCADE')."""
    channels = ForumChannel.query.filter(ForumChannel.retention_days.isnot(None)).all()
    total_deleted = 0
    for channel in channels:
        cutoff = datetime.utcnow() - timedelta(days=channel.retention_days)
        old = ForumMessage.query.filter(
            ForumMessage.channel_id == channel.id,
            ForumMessage.timestamp < cutoff,
        ).all()
        for msg in old:
            if msg.r2_key:
                from lms import r2_client
                r2_client.delete_object(msg.r2_key)
            db.session.delete(msg)
        total_deleted += len(old)
    db.session.commit()
    logger.info(f"Forum expiry sweep: checked {len(channels)} channel(s), deleted {total_deleted} message(s)")
    return {'channels_checked': len(channels), 'messages_deleted': total_deleted}
