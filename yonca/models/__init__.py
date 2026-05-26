"""
Database models for Yonca application
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

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
    preferred_language = db.Column(db.String(10), default='en')  # User's preferred language for translations
    google_access_token = db.Column(db.Text)
    google_refresh_token = db.Column(db.Text)
    google_token_expiry = db.Column(db.DateTime)
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

    def __repr__(self):
        return f'<User {self.username}>'

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, plaintext):
        self._password = generate_password_hash(plaintext)

    def check_password(self, plaintext):
        return check_password_hash(self._password, plaintext)

    def __repr__(self):
        return f'<User {self.username}>'

class Course(db.Model):
    """Course model for course management"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    time_slot = db.Column(db.String(100))
    profile_emoji = db.Column(db.String(10))
    # Dropdown menu items for non-logged-in users (configurable in admin)
    dropdown_menu = db.Column(db.JSON, default=[
        {"text": "Login to Enroll", "icon": "🔐", "url": "/login"},
        {"text": "View Details", "icon": "📖", "url": "#"}
    ])

    # Course page content (managed by admin)
    page_welcome_title = db.Column(db.String(200), default="")
    page_subtitle = db.Column(db.String(500), default="")
    page_description = db.Column(db.Text, default="")
    page_builder_data = db.Column(db.JSON, default=[])
    page_features = db.Column(db.JSON, default=[
        {"title": "Interactive Learning", "description": "Engage with dynamic course content and interactive exercises.", "image": ""},
        {"title": "Expert Guidance", "description": "Learn from industry professionals and experienced educators.", "image": ""},
        {"title": "Community Support", "description": "Connect with fellow learners and get help when you need it.", "image": ""}
    ])
    page_gallery_images = db.Column(db.JSON, default=[])
    page_show_navigation = db.Column(db.Boolean, default=True)
    page_show_footer = db.Column(db.Boolean, default=True)
    page_show_title = db.Column(db.Boolean, default=True)
    page_show_description = db.Column(db.Boolean, default=True)
    
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

    def __repr__(self):
        return f'<PDFDocument {self.title}>'

class HomeContent(db.Model):
    """Home page content model for configurable site content"""
    id = db.Column(db.Integer, primary_key=True)
    # Content for logged-in users
    welcome_title = db.Column(db.String(200), default="Welcome to Yonca")
    subtitle = db.Column(db.String(500), default="Your gateway to knowledge and community learning.")
    get_started_text = db.Column(db.String(200), default="Get Started")
    features = db.Column(db.JSON, default=[
        {"title": "Courses", "description": "Access educational courses and learning materials."},
        {"title": "Community Forum", "description": "Connect with fellow learners, ask questions, and share knowledge."},
        {"title": "Learning Materials", "description": "Access educational resources and study materials."},
        {"title": "Secure PDF Library", "description": "Upload and access protected PDF documents."}
    ])
    # Content for logged-out users
    logged_out_welcome_title = db.Column(db.String(200), default="Welcome to Yonca")
    logged_out_subtitle = db.Column(db.String(500), default="Join our learning community today!")
    logged_out_get_started_text = db.Column(db.String(200), default="Sign Up Now")
    logged_out_features = db.Column(db.JSON, default=[
        {"title": "Free Courses", "description": "Access our free educational courses."},
        {"title": "Community", "description": "Join discussions with fellow learners."},
        {"title": "Resources", "description": "Browse our learning materials."},
        {"title": "Sign Up", "description": "Create your account to get started."}
    ])
    # Gallery images
    gallery_images = db.Column(db.JSON, default=[])
    
    # Section-specific content
    courses_section_title = db.Column(db.String(200), default="Our Courses")
    courses_section_description = db.Column(db.Text, default="Explore our comprehensive collection of educational courses designed to help you learn and grow.")
    
    forum_section_title = db.Column(db.String(200), default="Community Forum")
    forum_section_description = db.Column(db.Text, default="Connect with fellow learners, share knowledge, and get help from our active community.")
    
    resources_section_title = db.Column(db.String(200), default="Learning Resources")
    resources_section_description = db.Column(db.Text, default="Access a comprehensive library of learning materials, guides, and educational resources.")
    
    moxo_test_section_title = db.Column('tavi_test_section_title', db.String(200), default="MOXO Test")
    moxo_test_section_description = db.Column('tavi_test_section_description', db.Text, default="Take our interactive assessment to discover your learning style and get personalized recommendations.")
    
    contact_info = db.Column(db.JSON, default={
        "whatsapp": "+994 51 623 73 94",
        "email": "info@yonca.az",
        "address": "Baku, Azerbaijan"
    })
    
    about_section_title = db.Column(db.String(200), default="About Yonca")
    about_section_description = db.Column(db.Text, default="Yonca is a comprehensive learning platform dedicated to providing quality education and fostering a supportive learning community.")
    
    # About page specific content
    about_welcome_title = db.Column(db.String(200), default="Welcome to Yonca")
    about_subtitle = db.Column(db.Text, default="Join our learning community and discover amazing features designed to enhance your educational experience.")
    # Home page features title/subtitle (shown after gallery)
    features_title = db.Column(db.String(200), default="Our Features")
    features_subtitle = db.Column(db.String(500), default="Discover what makes our platform special.")
    about_gallery_images = db.Column(db.JSON, default=[])
    about_gallery_title = db.Column(db.String(200), default="What's New")
    about_gallery_subtitle = db.Column(db.String(500), default="Discover the latest updates, new features, and exciting developments in our learning platform.")
    
    # About gallery 2 section
    about_gallery_2_title = db.Column(db.String(200), default="Featured Content")
    about_gallery_2_subtitle = db.Column(db.String(500), default="Explore more exciting content and resources.")
    about_gallery_2_images = db.Column(db.JSON, default=[])
    
    # Navigation and branding
    site_logo_url = db.Column(db.String(500), default="https://lh3.googleusercontent.com/d/1abc123def456ghi789jkl012mno345pqr/view")
    site_name = db.Column(db.String(200), default="Yonca")
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
        return f'<HomeContent {self.id}>'

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
    content_type = db.Column(db.String(50), nullable=False)  # 'course', 'resource', 'home_content', 'gallery_item'
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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content_type = db.Column(db.String(50), nullable=False)  # 'course_content', 'resource', 'pdf', etc.
    content_id = db.Column(db.String(255), nullable=False)  # File / resource identifier (Google Drive ID)
    viewed_at = db.Column(db.DateTime, server_default=db.func.now())  # When viewing started
    viewing_duration = db.Column(db.Integer, default=0)  # Duration in seconds
    
    # Relationships
    user = db.relationship('User', backref=db.backref('content_views', lazy='dynamic'))

    def __repr__(self):
        return f'<ContentView {self.user_id}:{self.content_type}:{self.content_id}>'
