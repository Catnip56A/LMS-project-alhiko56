"""
Database models for LMS application
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime

db = SQLAlchemy()

# Association table for many-to-many relationship between User and Course
user_courses = db.Table('user_courses',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

# Association table for tracking which users have accessed which resources via PIN
user_resource_access = db.Table('user_resource_access',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('resource_id', db.Integer, db.ForeignKey('resource.id'), primary_key=True),
    db.Column('accessed_at', db.DateTime, server_default=db.func.now())
)

class User(db.Model, UserMixin):
    """User model for authentication and course enrollment"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)  # Made nullable for non-Google users
    _password = db.Column('password', db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_teacher = db.Column(db.Boolean, default=False)
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
    courses = db.relationship('Course', secondary=user_courses, backref=db.backref('users', lazy='select'))
    accessed_resources = db.relationship('Resource', secondary=user_resource_access, backref=db.backref('accessed_users', lazy='select'))

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

    def __repr__(self):
        return f'<Course {self.title}>'

class ForumMessage(db.Model):
    """Forum message model for community discussions"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    username = db.Column(db.String(80))
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    parent_id = db.Column(db.Integer, db.ForeignKey('forum_message.id'), nullable=True)
    channel = db.Column(db.String(50), default='general', nullable=False)  # Channel/category for the message
    
    # Relationship for replies
    replies = db.relationship('ForumMessage', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

    def __repr__(self):
        return f'<ForumMessage {self.id}>'

class ForumChannel(db.Model):
    """Forum channel model for organizing discussions"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Display name
    slug = db.Column(db.String(50), unique=True, nullable=False)  # URL-friendly identifier
    description = db.Column(db.Text)
    requires_login = db.Column(db.Boolean, default=False)  # Whether login is required
    admin_only = db.Column(db.Boolean, default=False)  # Whether admin access is required
    is_active = db.Column(db.Boolean, default=True)  # Whether channel is visible
    sort_order = db.Column(db.Integer, default=0)  # Display order
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    def __repr__(self):
        return f'<ForumChannel {self.name} ({self.slug})>'


class CourseAssignmentSubmission(db.Model):
    """Assignment submission model for student uploads"""
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('course_assignment.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_path = db.Column(db.String(300), nullable=True)  # Legacy field, now nullable
    drive_file_id = db.Column(db.String(100))  # Google Drive file ID
    drive_view_link = db.Column(db.String(300))  # Google Drive view link
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

class Resource(db.Model):
    """Resource model for learning materials"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    tags = db.Column(db.String(500))  # Space-separated tags
    preview_image = db.Column(db.String(300))  # Preview image URL or path
    preview_drive_file_id = db.Column(db.String(100))  # Google Drive file ID for preview image
    preview_drive_view_link = db.Column(db.String(300))  # Google Drive view link for preview image
    drive_file_id = db.Column(db.String(100))  # Google Drive file ID
    drive_view_link = db.Column(db.String(300))  # Google Drive view link
    is_image_file = db.Column(db.Boolean, default=False)  # Whether the main file is an image
    access_pin = db.Column(db.String(10), nullable=True)
    pin_expires_at = db.Column(db.DateTime, nullable=True)
    pin_last_reset = db.Column(db.DateTime, server_default=db.func.now())
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    upload_date = db.Column(db.DateTime, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True)
    allow_others_to_view = db.Column(db.Boolean, default=True)  # Allow other users to view this file
    is_imported = db.Column(db.Boolean, default=False)  # True = imported from user's Drive, do not delete from Drive on removal

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate initial random PIN and expiration time
        if not self.access_pin:
            self.generate_new_pin()

    def generate_new_pin(self):
        """Generate a new random 6-character PIN and set expiration to 10 minutes from now"""
        import random
        import string
        from datetime import datetime, timedelta

        self.access_pin = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        self.pin_expires_at = datetime.utcnow() + timedelta(minutes=10)
        self.pin_last_reset = datetime.utcnow()

    def is_pin_expired(self):
        """Check if the current PIN has expired"""
        from datetime import datetime
        if not self.access_pin:
            return False  # No PIN means no expiration
        return datetime.utcnow() > self.pin_expires_at

    def reset_pin(self):
        """Reset the PIN with a new random value and 10-minute expiration"""
        if self.access_pin:  # Only reset if there's currently a PIN
            self.generate_new_pin()

    def __repr__(self):
        return f'<Resource {self.title}>'

class MoxoTest(db.Model):
    """Test result model for user assessments"""
    __tablename__ = 'tavi_test'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    result = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<MoxoTest {self.id}>'

class PDFDocument(db.Model):
    """PDF document model for secure document management"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300), nullable=False)
    drive_file_id = db.Column(db.String(100))  # Google Drive file ID
    drive_view_link = db.Column(db.String(300))  # Google Drive view link
    file_size = db.Column(db.Integer)
    access_pin = db.Column(db.String(10), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    upload_date = db.Column(db.DateTime, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True)
    allow_others_to_view = db.Column(db.Boolean, default=True)  # Allow other users to view this file
    is_imported = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<PDFDocument {self.title}>'

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
        {"name": "MOXO Test", "url": "/#moxo", "active": True},
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
    drive_file_id = db.Column(db.String(100))  # Google Drive file ID for file content
    drive_view_link = db.Column(db.String(300))  # Google Drive view link for file content
    order = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    allow_others_to_view = db.Column(db.Boolean, default=True)  # Allow other users to view this file
    is_imported = db.Column(db.Boolean, default=False)
    is_downloadable = db.Column(db.Boolean, default=False)

    course = db.relationship('Course', backref=db.backref('contents', lazy='dynamic'))
    folder_id = db.Column(db.Integer, db.ForeignKey('course_content_folder.id'), nullable=True)
    folder = db.relationship('CourseContentFolder', backref=db.backref('items', lazy='select'))
    
    def __repr__(self):
        return f'<CourseContent {self.title}>'

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

class CourseAnnouncement(db.Model):
    """Course announcements/messages"""
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    course = db.relationship('Course', backref=db.backref('announcements', lazy='dynamic'))
    author = db.relationship('User')
    
    def __repr__(self):
        return f'<CourseAnnouncement {self.title}>'


class CourseAnnouncementReply(db.Model):
    """Replies/messages sent to course announcements"""
    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('course_announcement.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_reply_id = db.Column(db.Integer, db.ForeignKey('course_announcement_reply.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    announcement = db.relationship('CourseAnnouncement', backref=db.backref('replies', lazy='select'))
    user = db.relationship('User')
    parent_reply = db.relationship('CourseAnnouncementReply', remote_side=[id], backref=db.backref('child_replies', lazy='select'))

    def __repr__(self):
        return f'<CourseAnnouncementReply {self.id}>'


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
