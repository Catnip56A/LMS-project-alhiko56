"""
Database models for LMS application
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from pgvector.sqlalchemy import Vector
from sqlalchemy.ext.associationproxy import association_proxy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime, timedelta

# Dimensionality requested from Gemini's embedding model (embed_content, outputDimensionality)
# — the model's native output is 3072-dim; truncating to 768 keeps storage/search cheap for
# this project's scale and stays under pgvector's 2000-dim HNSW index ceiling if one is added
# later. Values are re-normalized after truncation (Google's own requirement at this size).
EMBEDDING_DIMENSIONS = 768

db = SQLAlchemy()

# How a user ended up enrolled in a course (Enrollment.joined_via) — one of the
# non-exclusive join paths from the access & enrollment model.
JOIN_VIA_PROMO_CODE = 'promo_code'
JOIN_VIA_DIRECT_LINK = 'direct_link'
JOIN_VIA_DIRECT_ADD = 'direct_add'
JOIN_VIA_INSTANT_PUBLIC = 'instant_public'
JOIN_VIA_CREATOR = 'creator'

# Valid QuizQuestion.question_type values — enforced by a DB CHECK constraint (defense in
# depth for any write path) and restricted to a dropdown in the admin form (see admin/__init__.py).
QUIZ_QUESTION_TYPES = ('mcq', 'true_false', 'short_answer')

class User(db.Model, UserMixin):
    """User model for authentication and course enrollment"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)  # Made nullable for non-Google users
    _password = db.Column('password', db.String(200), nullable=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))
    is_admin = db.Column(db.Boolean, default=False)
    admin_permissions = db.Column(db.JSON, nullable=True)
    preferred_language = db.Column(db.String(10), default='en')  # User's preferred language for translations
    google_access_token = db.Column(db.Text)
    google_refresh_token = db.Column(db.Text)
    google_token_expiry = db.Column(db.DateTime)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, server_default=db.func.now())
    login_attempts = db.Column(db.Integer, default=0)  # Track failed login attempts
    last_attempt_time = db.Column(db.DateTime)  # Track time of last login attempt
    # AI "Ask AI" conversation history consent — NULL means not asked yet (prompt shown on
    # next use), True/False is a standing per-user choice. See AiConversation.
    ai_history_consent = db.Column(db.Boolean, nullable=True)
    enrollments = db.relationship('Enrollment', back_populates='user', cascade='all, delete-orphan')
    courses = association_proxy('enrollments', 'course', creator=lambda course: Enrollment(course=course))

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, plaintext):
        self._password = generate_password_hash(plaintext)

    def check_password(self, plaintext):
        return check_password_hash(self._password, plaintext)

    @property
    def any_admin(self):
        """True if the user has any admin access (is_admin must be True)."""
        return self.is_admin

    @property
    def is_full_admin(self):
        """True if unrestricted admin: is_admin=True and no permission restrictions set."""
        return self.is_admin and self.admin_permissions is None

    def has_perm(self, perm: str) -> bool:
        """True if is_admin with no restrictions, or if perm is in admin_permissions list."""
        if not self.is_admin:
            return False
        if self.admin_permissions is None:
            return True  # full admin — unrestricted
        return perm in self.admin_permissions

    def __repr__(self):
        return f'<User {self.username}>'

class Course(db.Model):
    """Course model for course management"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    time_slot = db.Column(db.String(100))
    profile_emoji = db.Column(db.String(10))

    # Tags for course filtering
    tags = db.Column(db.JSON, default=[])

    # Open-source/public flag: visible and instantly joinable by any user, not just enrollees
    is_public = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))

    # Self-service creator, if any — NULL for courses created via the admin panel (pre-existing
    # or admin-created). Lets a non-admin/non-teacher user manage the specific course they made.
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    creator = db.relationship('User', foreign_keys=[created_by])

    enrollments = db.relationship('Enrollment', back_populates='course', cascade='all, delete-orphan')
    users = association_proxy('enrollments', 'user', creator=lambda user: Enrollment(user=user))

    def is_managed_by(self, user):
        """True if `user` can manage this specific course: any admin (global rights), the
        course's creator, or a user assigned as a teacher for this specific course (via
        Enrollment.is_teacher — see is_owned_by for who can grant that)."""
        if not user or not user.is_authenticated:
            return False
        if user.is_admin or self.created_by == user.id:
            return True
        enrollment = Enrollment.query.filter_by(course_id=self.id, user_id=user.id).first()
        return bool(enrollment and enrollment.is_teacher)

    def is_owned_by(self, user):
        """True if `user` can transfer ownership or assign/unassign co-teachers for this
        course: an admin, or this course's creator specifically (not just any teacher)."""
        if not user or not user.is_authenticated:
            return False
        return user.is_admin or self.created_by == user.id

    def __repr__(self):
        return f'<Course {self.title}>'


class Enrollment(db.Model):
    """Join-object between User and Course — tracks how/when someone joined.

    Replaces the old plain user_courses association table so each membership
    can record its join path (see JOIN_VIA_* constants) instead of just the fact
    of membership. `paid` is a stub for future paid enrollment (not used yet).
    """
    __tablename__ = 'enrollment'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id', ondelete='CASCADE'), nullable=False)
    joined_via = db.Column(db.String(30), nullable=False, default=JOIN_VIA_DIRECT_ADD, server_default=JOIN_VIA_DIRECT_ADD)
    enrolled_at = db.Column(db.DateTime, server_default=db.func.now())
    promo_code_id = db.Column(db.Integer, db.ForeignKey('promo_code.id'), nullable=True)
    paid = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))
    # Per-course teacher role — assigned by the course's creator or an admin (see
    # Course.is_managed_by). Replaces the old global User.is_teacher flag.
    is_teacher = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))
    # Blocks this student from flagging video moments in this course (see VideoMomentFlag) —
    # a teacher-set moderation flag, per-course like is_teacher, not a global ban.
    moment_flags_blocked = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))

    __table_args__ = (db.UniqueConstraint('user_id', 'course_id', name='uq_enrollment_user_course'),)

    user = db.relationship('User', back_populates='enrollments')
    course = db.relationship('Course', back_populates='enrollments')
    promo_code = db.relationship('PromoCode', backref=db.backref('enrollments', lazy='select'))

    def __repr__(self):
        return f'<Enrollment user={self.user_id} course={self.course_id} via={self.joined_via}>'


class PromoCode(db.Model):
    """Promo code issued by an admin/teacher to let people join a course without
    being directly added. Redeemed via the code itself (typed) or a direct link
    that wraps the same code — both are join paths for the same PromoCode row.
    """
    __tablename__ = 'promo_code'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id', ondelete='CASCADE'), nullable=False)
    code = db.Column(db.String(40), unique=True, nullable=False)
    max_uses = db.Column(db.Integer, nullable=True)  # None = unlimited
    uses_count = db.Column(db.Integer, nullable=False, default=0)
    issued_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    course = db.relationship('Course', backref=db.backref('promo_codes', lazy='select', cascade='all, delete-orphan'))
    issued_by = db.relationship('User', foreign_keys=[issued_by_id])

    @property
    def is_valid(self):
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        if self.max_uses is not None and self.uses_count >= self.max_uses:
            return False
        return True

    def __repr__(self):
        return f'<PromoCode {self.code}>'

class ForumMessage(db.Model):
    """Forum message model for community discussions — used for global channels, course
    channels (replacing the old CourseAnnouncement/CourseAnnouncementReply pair), moderator
    Groups, and private 1:1 DMs alike (see ForumChannel.channel_type)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    username = db.Column(db.String(80))
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    # ondelete='CASCADE': deleting a message deliberately takes its replies with it (used by
    # the hard-delete expiry sweep and moderator "clear history" action — single-message
    # moderator/author deletion is a soft delete instead, specifically so this cascade never
    # fires from that action and orphans nothing).
    parent_id = db.Column(db.Integer, db.ForeignKey('forum_message.id', ondelete='CASCADE'), nullable=True)
    # Real FK, not a bare string — a prior version of this model stored `channel` as a plain
    # string with no referential integrity to ForumChannel at all.
    channel_id = db.Column(db.Integer, db.ForeignKey('forum_channel.id'), nullable=False)
    pinned = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))
    # Soft-delete marker for manual per-message deletion (moderator or the author) — the row
    # stays so reply threads don't orphan; rendered as a "[message deleted]" placeholder.
    deleted_at = db.Column(db.DateTime, nullable=True)

    # Relationship for replies
    # passive_deletes=True: let the DB's ON DELETE CASCADE (see parent_id's FK, migration
    # d0e1f2a3b4c5) actually delete replies when their parent is deleted. Without this,
    # SQLAlchemy's default behavior is to UPDATE each loaded child's parent_id to NULL before
    # issuing the parent's DELETE — satisfying the ORM's own bookkeeping, but running before
    # the DB-level cascade ever gets a chance to fire, silently orphaning replies instead of
    # removing them (found live: a hard-deleted parent left its reply behind with parent_id
    # NULL rather than gone).
    replies = db.relationship(
        'ForumMessage', backref=db.backref('parent', remote_side=[id]),
        lazy='dynamic', passive_deletes=True,
    )
    forum_channel = db.relationship('ForumChannel', backref=db.backref('messages', lazy='dynamic'))

    def __repr__(self):
        return f'<ForumMessage {self.id}>'

class ForumChannel(db.Model):
    """Forum channel model — covers global channels (the original use), course-scoped
    channels, moderator-created Groups, and private 1:1 DMs, all via channel_type."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Display name
    slug = db.Column(db.String(50), unique=True, nullable=False)  # URL-friendly identifier
    description = db.Column(db.Text)
    requires_login = db.Column(db.Boolean, default=False)  # Whether login is required
    admin_only = db.Column(db.Boolean, default=False)  # Whether admin access is required
    is_active = db.Column(db.Boolean, default=True)  # Whether channel is visible
    is_public = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('false'))  # Open-source/public: visible to non-enrolled users
    sort_order = db.Column(db.Integer, default=0)  # Display order
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    # 'global' (the original/default kind) | 'course' | 'group' | 'dm'
    channel_type = db.Column(db.String(20), nullable=False, default='global', server_default="'global'")
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)  # set only for channel_type='course'
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # NULL for the original global channels
    # 'open' (anyone logged in can view/post, same as the existing requires_login/is_public/
    # admin_only gates) | 'invite_only' (gated by ForumChannelMembership rows). Meaningful only
    # for channel_type='group' — NULL for global/course channels (existing gates apply), and a
    # 'dm' channel is implicitly always membership-gated regardless of this field.
    membership_mode = db.Column(db.String(20), nullable=True)
    retention_days = db.Column(db.Integer, nullable=True)  # NULL = never auto-expire

    course = db.relationship('Course', backref=db.backref('forum_channels', lazy='dynamic'))

    def __repr__(self):
        return f'<ForumChannel {self.name} ({self.slug})>'


class ForumChannelMembership(db.Model):
    """Explicit membership row — used unconditionally for channel_type='dm' (exactly 2 rows)
    and for channel_type='group' with membership_mode='invite_only' (gates view/post access).
    Not consulted for 'open' groups or global/course channels, which use ForumChannel's
    existing requires_login/is_public/admin_only/course-enrollment gates instead."""
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('forum_channel.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, server_default=db.func.now())

    channel = db.relationship('ForumChannel', backref=db.backref('memberships', lazy='dynamic'))
    user = db.relationship('User')

    __table_args__ = (db.UniqueConstraint('channel_id', 'user_id', name='uq_forum_channel_membership'),)

    def __repr__(self):
        return f'<ForumChannelMembership channel={self.channel_id} user={self.user_id}>'


class CourseAssignmentSubmission(db.Model):
    """Assignment submission model for student uploads"""
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('course_assignment.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_path = db.Column(db.String(300), nullable=True)  # Legacy field, now nullable
    drive_file_id = db.Column(db.String(100))  # Google Drive file ID — provenance only once r2_key is set
    drive_view_link = db.Column(db.String(300))  # Google Drive view link
    r2_key = db.Column(db.String(500), nullable=True)  # Cloudflare R2 object key — wins over Drive when set
    r2_preview_key = db.Column(db.String(500), nullable=True)  # Converted-PDF preview for Office-format submissions
    file_mime_type = db.Column(db.String(150), nullable=True)  # Sniffed from bytes at upload time
    submitted_at = db.Column(db.DateTime, server_default=db.func.now())
    grade = db.Column(db.Integer, nullable=True)
    comment = db.Column(db.Text, nullable=True)
    passed = db.Column(db.Boolean, default=False)
    allow_others_to_view = db.Column(db.Boolean, default=False)  # Allow other users to view this file
    declined = db.Column(db.Boolean, default=False)  # Submission declined by teacher/admin
    assignment = db.relationship('CourseAssignment', backref=db.backref('submissions', lazy='select'))
    user = db.relationship('User')

    def __repr__(self):
        return f'<CourseAssignmentSubmission {self.id}>'

class SiteSettings(db.Model):
    """Minimal site branding settings (name, logo, contact, navigation)."""
    id = db.Column(db.Integer, primary_key=True)

    site_logo_url = db.Column(db.String(500), default="")
    site_name = db.Column(db.String(200), default="LMS")
    contact_info = db.Column(db.JSON, default={
        "whatsapp": "",
        "email": "info@example.com",
        "address": ""
    })
    navigation_items = db.Column(db.JSON, default=[
        {"name": "Home", "url": "/", "active": True},
        {"name": "Courses", "url": "/#courses", "active": True},
        {"name": "Forum", "url": "/#forum", "active": True},
        {"name": "Resources", "url": "/#resources", "active": True},
        {"name": "About", "url": "/#about", "active": True}
    ])

    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<SiteSettings {self.id}>'

class Translation(db.Model):
    """Translation cache model for AI-powered translations"""
    id = db.Column(db.Integer, primary_key=True)
    source_text = db.Column(db.Text, nullable=False)
    source_language = db.Column(db.String(10), default='auto')  # 'auto' for auto-detection
    target_language = db.Column(db.String(10), nullable=False)
    translated_text = db.Column(db.Text, nullable=False)
    translation_service = db.Column(db.String(50), default='google')  # Service used for translation
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Index for fast lookups
    __table_args__ = (
        db.Index('idx_translation_lookup', 'source_text', 'target_language'),
    )

    def __repr__(self):
        return f'<Translation {self.source_language}->{self.target_language}: {self.source_text[:50]}>'

class ContentTranslation(db.Model):
    """Content translation model for dynamic content (courses, resources, gallery, etc.)"""
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(50), nullable=False)  # 'course', 'resource'
    content_id = db.Column(db.Integer, nullable=False)  # ID of the content item
    field_name = db.Column(db.String(100), nullable=False)  # Field being translated (e.g., 'title', 'description')
    source_language = db.Column(db.String(10), default='en')  # Source language
    target_language = db.Column(db.String(10), nullable=False)  # Target language ('ru')
    translated_text = db.Column(db.Text, nullable=False)  # Translated content
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    
    # Index for fast lookups
    __table_args__ = (
        db.Index('idx_content_translation_lookup', 'content_type', 'content_id', 'field_name', 'target_language'),
    )

    def __repr__(self):
        return f'<ContentTranslation {self.content_type}:{self.content_id}.{self.field_name} -> {self.target_language}>'

class CourseContent(db.Model):
    """Course content modules/sections"""
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    content_type = db.Column(db.String(50), default='text')  # text, video, file, link
    content_data = db.Column(db.Text)  # URL, file path, or text content for non-file types
    drive_file_id = db.Column(db.String(100))  # Google Drive file ID; provenance only once r2_key is set, never cleared
    drive_view_link = db.Column(db.String(300))  # Google Drive view link for file content
    r2_key = db.Column(db.String(512))  # Object key in the R2 bucket; NULL = bytes not migrated to R2 yet
    r2_preview_key = db.Column(db.String(512))  # Converted-to-PDF preview for Office docs the browser can't render raw (see lms/office_preview.py); NULL if the original is natively viewable
    file_mime_type = db.Column(db.String(150))  # Sniffed/authoritative MIME type; NULL for legacy rows
    order = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    allow_others_to_view = db.Column(db.Boolean, default=True)  # Allow other users to view this file
    is_imported = db.Column(db.Boolean, default=False)
    is_downloadable = db.Column(db.Boolean, default=False)
    embedded_at = db.Column(db.DateTime, nullable=True)  # Set once the RAG embedding sweep has indexed this item
    transcript_language = db.Column(db.String(10), nullable=True)  # Whisper's detected language (e.g. 'en'/'ru'); NULL until transcribed, or for non-video/audio content

    course = db.relationship('Course', backref=db.backref('contents', lazy='dynamic'))
    folder_id = db.Column(db.Integer, db.ForeignKey('course_content_folder.id'), nullable=True)
    folder = db.relationship('CourseContentFolder', backref=db.backref('items', lazy='select'))

    def __repr__(self):
        return f'<CourseContent {self.title}>'

    @property
    def has_bytes(self):
        """True if this row's file bytes are retrievable from some backend (R2 or Drive)."""
        return bool(self.r2_key or self.drive_file_id)

    @property
    def storage_backend(self):
        """'r2' | 'drive' | None. R2 wins when both are set — drive_file_id is retained as
        provenance only once a row has been migrated, never cleared."""
        if self.r2_key:
            return 'r2'
        if self.drive_file_id:
            return 'drive'
        return None


class ContentEmbedding(db.Model):
    """One chunk of a CourseContent item's text, embedded for RAG retrieval (Phase 6)."""
    id = db.Column(db.Integer, primary_key=True)
    course_content_id = db.Column(db.Integer, db.ForeignKey('course_content.id'), nullable=False)
    chunk_index = db.Column(db.Integer, nullable=False)
    chunk_text = db.Column(db.Text, nullable=False)
    embedding = db.Column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    # Only set for chunks produced from timestamped video/audio transcripts (see
    # rag_service.chunk_segments_by_time) — NULL for plain text/PDF/DOCX/PPTX chunks, which
    # have no time axis. Lets Ask AI citations point at a moment in a video, not just the file.
    start_seconds = db.Column(db.Float, nullable=True)
    end_seconds = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    course_content = db.relationship(
        'CourseContent',
        backref=db.backref('embeddings', lazy='dynamic', cascade='all, delete-orphan'),
    )

    __table_args__ = (
        db.UniqueConstraint('course_content_id', 'chunk_index', name='uq_content_embedding_chunk'),
    )

    def __repr__(self):
        return f'<ContentEmbedding content={self.course_content_id} chunk={self.chunk_index}>'


class VideoMomentFlag(db.Model):
    """One raw signal — an automatic keyword hit or a student click — that a moment in a
    video might be worth highlighting (Phase 6 addendum, video moment highlighting).

    Append-only audit log, deliberately kept separate from VideoMoment (the promoted,
    citable artifact): this table is high-volume and never mutated, while VideoMoment is
    low-volume and has real state (caption, status, retry count). Collapsing them would mean
    a spam-flag delete could risk an already-embedded caption, and would make "a student
    clicked" indistinguishable from "a citable artifact exists".
    """
    id = db.Column(db.Integer, primary_key=True)
    course_content_id = db.Column(db.Integer, db.ForeignKey('course_content.id'), nullable=False)
    timestamp_seconds = db.Column(db.Float, nullable=False)
    # floor(timestamp_seconds / SEGMENT_CHUNK_WINDOW_SECONDS) — see moment_service.bucket_for.
    # Stored (not computed at query time) so "one flag per student per moment" can be a plain
    # DB unique constraint below, and weight a plain indexed GROUP BY.
    bucket_index = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(20), nullable=False)  # 'auto' | 'student'
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # NULL for source='auto'
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    course_content = db.relationship(
        'CourseContent',
        backref=db.backref('moment_flags', lazy='dynamic', cascade='all, delete-orphan'),
    )

    __table_args__ = (
        # The real anti-spam primitive: one flag per student per bucket per video, enforced by
        # Postgres. Does NOT dedupe source='auto' rows (added_by is NULL for all of them, and
        # Postgres treats NULLs as distinct in a unique constraint) — auto idempotency is
        # instead handled by delete-and-reinsert in moment_service.record_auto_moments.
        db.UniqueConstraint('course_content_id', 'bucket_index', 'added_by', name='uq_video_moment_flag_bucket_user'),
        db.Index('idx_video_moment_flag_bucket', 'course_content_id', 'bucket_index'),
    )

    def __repr__(self):
        return f'<VideoMomentFlag content={self.course_content_id} bucket={self.bucket_index} source={self.source}>'


class VideoMoment(db.Model):
    """A promoted, citable moment in a video — created once a VideoMomentFlag bucket crosses
    its course's weighting threshold (or a teacher flags it directly). Captioned via AI vision
    once, then re-embedded into ContentEmbedding on every reindex without another API call.
    """
    id = db.Column(db.Integer, primary_key=True)
    course_content_id = db.Column(db.Integer, db.ForeignKey('course_content.id'), nullable=False)
    # The bucket this moment claims — identity for the sweep's anti-join and for teacher
    # blocking. timestamp_seconds is the refined payload (may differ from the bucket's
    # nominal start once the frame-analysis pass picks an exact moment within it).
    bucket_index = db.Column(db.Integer, nullable=False)
    timestamp_seconds = db.Column(db.Float, nullable=False)
    weight_at_promotion = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending | captioned | failed | blocked
    caption = db.Column(db.Text, nullable=True)
    frame_phash = db.Column(db.String(32), nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_attempt_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    captioned_at = db.Column(db.DateTime, nullable=True)

    course_content = db.relationship(
        'CourseContent',
        backref=db.backref('moments', lazy='dynamic', cascade='all, delete-orphan'),
    )

    __table_args__ = (
        db.UniqueConstraint('course_content_id', 'bucket_index', name='uq_video_moment_bucket'),
    )

    def __repr__(self):
        return f'<VideoMoment content={self.course_content_id} bucket={self.bucket_index} status={self.status}>'


class TranscriptSegment(db.Model):
    """One Whisper-transcribed segment (~2-8s) of a video/audio CourseContent's spoken
    audio, persisted specifically for subtitle generation (see lms/subtitle_service.py).
    embed_content_item's own RAG chunking (chunk_segments_by_time) collapses the same
    segments into much coarser ~45s windows for retrieval — that's the right grain for
    citations, but far too coarse for subtitles, which need this original per-segment
    timing. Populated as a side effect of transcription in embed_content_item; deleted and
    re-inserted on every reindex, mirroring ContentEmbedding's own idempotency pattern.
    """
    id = db.Column(db.Integer, primary_key=True)
    course_content_id = db.Column(db.Integer, db.ForeignKey('course_content.id'), nullable=False)
    segment_index = db.Column(db.Integer, nullable=False)
    start_seconds = db.Column(db.Float, nullable=False)
    end_seconds = db.Column(db.Float, nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    course_content = db.relationship(
        'CourseContent',
        backref=db.backref('transcript_segments', lazy='dynamic', cascade='all, delete-orphan'),
    )

    __table_args__ = (
        db.UniqueConstraint('course_content_id', 'segment_index', name='uq_transcript_segment_index'),
    )

    def __repr__(self):
        return f'<TranscriptSegment content={self.course_content_id} idx={self.segment_index}>'


class AiConversation(db.Model):
    """One "Ask AI" conversation thread per (user, course). Always created/updated while a
    chat is active — needed for multi-turn memory within a session regardless of consent —
    but only ever displayed back to the user on a later visit if User.ai_history_consent is
    True. Not-consented (False or still-unanswered) conversations are purged 30 days after
    last_activity_at by a recurring job (see job_manager.py)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    summary = db.Column(db.Text, nullable=True)  # rolling compacted summary of older turns
    last_activity_at = db.Column(db.DateTime, server_default=db.func.now())
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship('User', backref=db.backref('ai_conversations', lazy='dynamic', cascade='all, delete-orphan'))
    course = db.relationship('Course')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='uq_ai_conversation_user_course'),
    )

    def __repr__(self):
        return f'<AiConversation user={self.user_id} course={self.course_id}>'


class AiConversationMessage(db.Model):
    """One turn in an AiConversation. Older turns get folded into the conversation's rolling
    summary and deleted once the raw count exceeds a threshold (see rag_service.py) —
    recent turns stay verbatim so citations can still be shown when history is reloaded."""
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('ai_conversation.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    sources = db.Column(db.JSON, nullable=True)  # assistant messages only: [{'content_id', 'title'}]
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    conversation = db.relationship(
        'AiConversation',
        backref=db.backref('messages', lazy='dynamic', order_by='AiConversationMessage.created_at', cascade='all, delete-orphan'),
    )

    def __repr__(self):
        return f'<AiConversationMessage conversation={self.conversation_id} role={self.role}>'


class CourseContentFolder(db.Model):
    """Folders for organizing course content"""
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    parent_folder_id = db.Column(db.Integer, db.ForeignKey('course_content_folder.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    course = db.relationship('Course', backref=db.backref('content_folders', lazy='dynamic'))
    parent_folder = db.relationship('CourseContentFolder', remote_side=[id], backref=db.backref('subfolders', lazy='select'))
    locked_until_assignment_id = db.Column(db.Integer, db.ForeignKey('course_assignment.id'), nullable=True)
    locked_until_assignment = db.relationship('CourseAssignment', foreign_keys=[locked_until_assignment_id])
    locked_until_quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=True)
    locked_until_quiz = db.relationship('Quiz', foreign_keys=[locked_until_quiz_id])

    def __repr__(self):
        return f'<CourseContentFolder {self.title}>'

class CourseAssignment(db.Model):
    """Course assignments"""
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime)
    points = db.Column(db.Integer, default=100)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    course = db.relationship('Course', backref=db.backref('assignments', lazy='dynamic'))

    def __repr__(self):
        return f'<CourseAssignment {self.title}>'


def _check_quiz_answer(question, submitted):
    """Auto-grade a single mcq/true_false answer against its question's correct_answer.
    short_answer is graded manually by a teacher instead — see QuizAttempt.grade()."""
    if question.question_type == 'mcq':
        return submitted == question.correct_answer
    if question.question_type == 'true_false':
        return bool(submitted) == bool(question.correct_answer)
    return False


class Quiz(db.Model):
    """Quiz belonging to a course — MCQ, true/false, and short-answer questions."""
    __tablename__ = 'quiz'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    time_limit_minutes = db.Column(db.Integer, nullable=True)  # None = untimed
    max_attempts = db.Column(db.Integer, nullable=True)  # None = unlimited
    passing_score = db.Column(db.Integer, nullable=False, default=70)  # percentage
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    course = db.relationship('Course', backref=db.backref('quizzes', lazy='dynamic'))

    def __repr__(self):
        return f'<Quiz {self.title}>'


class QuizQuestion(db.Model):
    """A single question on a Quiz. `correct_answer` shape depends on question_type:
    mcq -> index into `options`; true_false -> bool; short_answer -> case-insensitive string match.
    """
    __tablename__ = 'quiz_question'
    __table_args__ = (
        db.CheckConstraint(
            "question_type IN ('mcq', 'true_false', 'short_answer')",
            name='ck_quiz_question_type'),
    )
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id', ondelete='CASCADE'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False, default='mcq')  # mcq | true_false | short_answer
    options = db.Column(db.JSON, nullable=True)  # mcq only: list[str]
    correct_answer = db.Column(db.JSON, nullable=False)
    points = db.Column(db.Integer, nullable=False, default=1)
    order = db.Column(db.Integer, nullable=False, default=0)

    quiz = db.relationship('Quiz', backref=db.backref(
        'questions', lazy='select', order_by='QuizQuestion.order', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<QuizQuestion {self.id}>'


class QuizAttempt(db.Model):
    """One student's attempt at a Quiz. Graded once, at submission."""
    __tablename__ = 'quiz_attempt'
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    started_at = db.Column(db.DateTime, server_default=db.func.now())
    submitted_at = db.Column(db.DateTime, nullable=True)
    score = db.Column(db.Integer, nullable=True)  # percentage 0-100, set on submit
    passed = db.Column(db.Boolean, nullable=True)  # set on submit; drives folder gating like CourseAssignmentSubmission.passed

    quiz = db.relationship('Quiz', backref=db.backref('attempts', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User')

    @property
    def deadline(self):
        if self.quiz.time_limit_minutes is None:
            return None
        return self.started_at + timedelta(minutes=self.quiz.time_limit_minutes)

    @property
    def is_expired(self):
        deadline = self.deadline
        return deadline is not None and datetime.utcnow() > deadline

    def grade(self):
        """Auto-grade mcq/true_false answers immediately. Short-answer questions are left
        pending (is_correct=None) for manual teacher review instead — free-text answers can
        be correct without matching the stored string exactly, so auto-grading them as wrong
        would unfairly fail students. score/passed stay None while any answer is still
        pending; see needs_manual_review / grade_short_answer. Caller commits."""
        questions = {q.id: q for q in self.quiz.questions}
        for answer in self.answers:
            question = questions.get(answer.question_id)
            if question is None:
                continue
            if question.question_type == 'short_answer':
                answer.is_correct = None
                answer.points_awarded = 0
            else:
                correct = _check_quiz_answer(question, answer.answer)
                answer.is_correct = correct
                answer.points_awarded = question.points if correct else 0
        self.submitted_at = datetime.utcnow()
        self._finalize_score_if_ready()

    @property
    def needs_manual_review(self):
        """True if any answer (necessarily short_answer — see grade()) is still awaiting a
        teacher's Correct/Incorrect call."""
        return any(a.is_correct is None for a in self.answers)

    def grade_short_answer(self, question_id, is_correct):
        """Teacher manually grades one short-answer question on this attempt, then
        recomputes score/passed if every answer is now reviewed. Caller commits."""
        answer = next((a for a in self.answers if a.question_id == question_id), None)
        if not answer:
            return
        answer.is_correct = is_correct
        answer.points_awarded = answer.question.points if is_correct else 0
        self._finalize_score_if_ready()

    def _finalize_score_if_ready(self):
        """Sets score/passed once no answer is still pending manual review; leaves them None
        (pending) otherwise. Called from grade() at submission and again after each manual
        short-answer grade."""
        if self.needs_manual_review:
            self.score = None
            self.passed = None
            return
        questions = {q.id: q for q in self.quiz.questions}
        total_points = sum(q.points for q in questions.values()) or 1
        earned = sum(a.points_awarded for a in self.answers)
        self.score = round((earned / total_points) * 100)
        self.passed = self.score >= self.quiz.passing_score

    def __repr__(self):
        return f'<QuizAttempt quiz={self.quiz_id} user={self.user_id}>'


class QuizAnswer(db.Model):
    """A student's answer to one question within a QuizAttempt."""
    __tablename__ = 'quiz_answer'
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('quiz_attempt.id', ondelete='CASCADE'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_question.id', ondelete='CASCADE'), nullable=False)
    answer = db.Column(db.JSON, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    points_awarded = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('attempt_id', 'question_id', name='uq_quiz_answer_attempt_question'),)

    attempt = db.relationship('QuizAttempt', backref=db.backref(
        'answers', lazy='select', cascade='all, delete-orphan'))
    question = db.relationship('QuizQuestion')

    def __repr__(self):
        return f'<QuizAnswer attempt={self.attempt_id} question={self.question_id}>'


class CourseReview(db.Model):
    """Course reviews submitted by enrolled students"""
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    title = db.Column(db.String(200), nullable=False)
    review_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    
    course = db.relationship('Course', backref=db.backref('reviews', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('reviews', lazy='dynamic'))
    
    def __repr__(self):
        return f'<CourseReview {self.id} - {self.title}>'


class BackgroundJob(db.Model):
    """Model for tracking background jobs"""
    id = db.Column(db.String(36), primary_key=True)  # UUID as string
    type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued')  # queued, running, completed, failed
    progress = db.Column(db.Integer, default=0)  # 0-100
    message = db.Column(db.Text)
    data = db.Column(db.JSON)  # Job-type-specific input parameters (e.g. {'course_id': 5})
    result = db.Column(db.JSON)  # Store result data as JSON
    error = db.Column(db.Text)  # Store error message if failed
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        """Convert job to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'type': self.type,
            'status': self.status,
            'progress': self.progress,
            'message': self.message or '',
            'result': self.result,
            'error': self.error or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self):
        return f'<BackgroundJob {self.id} ({self.type})>'


class AppSetting(db.Model):
    """Application settings model for storing configuration values securely"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __repr__(self):
        return f'<AppSetting {self.key}>'


class ContentView(db.Model):
    """Model for tracking user views of course content"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    content_type = db.Column(db.String(50), nullable=False)  # 'course_content', 'resource', 'pdf', etc.
    content_id = db.Column(db.String(255), nullable=False)  # File / resource identifier (Google Drive ID)
    viewed_at = db.Column(db.DateTime, server_default=db.func.now())  # When viewing started
    viewing_duration = db.Column(db.Integer, default=0)  # Duration in seconds

    # Relationships
    user = db.relationship('User', backref=db.backref('content_views', lazy='dynamic', passive_deletes=True))

    def __repr__(self):
        return f'<ContentView {self.user_id}:{self.content_type}:{self.content_id}>'


class Certificate(db.Model):
    __tablename__ = 'certificates'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    issued_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    revoked_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    student_name = db.Column(db.String(200), nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])
    course = db.relationship('Course', foreign_keys=[course_id])

    @property
    def cert_id_display(self):
        short = self.id.replace('-', '').upper()[:5]
        year = self.issued_at.year
        return f"LMS-{year}-{short}"

    @property
    def verify_url(self):
        try:
            from flask import url_for
            return url_for('main.verify_certificate', cert_id=self.id, _external=True)
        except RuntimeError:
            return f"https://yourdomain.example.com/certificate/{self.id}"

    def __repr__(self):
        return f'<Certificate {self.cert_id_display}>'
