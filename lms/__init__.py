"""
Application factory and initialization
"""
from flask import Flask, request, redirect, url_for, jsonify
from flask_login import LoginManager
from flask_cors import CORS
from flask_session import Session
from flask_babel import Babel
from flask_wtf import CSRFProtect
from lms.logging_config import configure_logging
from lms.extensions import limiter
from lms.config import config
from lms.models import (
    db, User,
    Course as Course,
    ForumMessage as ForumMessage,
    ForumChannel as ForumChannel,
    PDFDocument as PDFDocument,
    MoxoTest as MoxoTest,
    Translation as Translation,
)
from flask_migrate import Migrate
from lms.admin import init_admin
from lms.routes.auth import auth_bp
from lms.routes.api import api_bp
from lms.routes import main_bp
import os
import psycopg2
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def create_database_if_not_exists(database_url):
    """Create PostgreSQL database if it doesn't exist"""
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip('/')

    # Connect to the default postgres database
    postgres_url = database_url.replace(f'/{db_name}', '/postgres')

    try:
        conn = psycopg2.connect(postgres_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cur.fetchone():
            cur.execute('CREATE DATABASE "%s"' % db_name)
            logger.info(f"Database {db_name} created.")
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error creating database: {e}")

def create_app(config_name='development'):
    """Create and configure Flask application"""
    # Get the package directory
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(package_dir)
    static_dir = os.path.join(project_root, 'static')
    template_dir = os.path.join(package_dir, 'templates')
    
    app = Flask(__name__, static_folder=static_dir, static_url_path='/static', template_folder=template_dir)

    # Load configuration
    app.config.from_object(config[config_name])

    # Configure structured (JSON, rotating) logging
    configure_logging(app)

    # Create PostgreSQL database if it doesn't exist
    # if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI']:
    #     create_database_if_not_exists(app.config['SQLALCHEMY_DATABASE_URI'])
    
    # Initialize extensions
    db.init_app(app)
    Migrate(app, db)
    
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.unauthorized_handler
    def unauthorized():
        """Handle unauthorized requests - return JSON for API, redirect for web"""
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required'}), 401
        next_url = request.path
        if request.query_string:
            next_url += '?' + request.query_string.decode()
        return redirect(url_for('auth.login', next=next_url))
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    # Initialize Babel for internationalization
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(package_dir, 'translations')
    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    
    babel = Babel(app)
    
    def get_locale():
        """Select the language for the current request"""
        from flask import request, session
        from lms.constants import SUPPORTED_LANGUAGES

        # Check URL parameter first
        lang = request.args.get('lang')
        if lang and lang in SUPPORTED_LANGUAGES:
            return lang

        # Check if language is set in session
        lang = session.get('language')
        if lang and lang in SUPPORTED_LANGUAGES:
            return lang

        # Default to English
        return 'en'
    
    # Set locale selector using the correct attribute
    babel.init_app(app, locale_selector=get_locale)
    
    # Helper function to check if the current request is on a legal page (privacy/terms)
    def _is_on_legal_page(request):
        """Check if the current request path is for privacy policy or terms of use"""
        path = request.path.lower()
        return path in ['/privacy', '/privacy-policy', '/terms', '/login']
    
    # Add Babel's _ function to Jinja2 globals for template translations
    from flask_babel import gettext as _gettext
    app.jinja_env.globals['_'] = _gettext
    
    # Add custom Jinja2 filter to convert \n escape sequences to actual newlines
    from markupsafe import Markup
    def nl2br_filter(text):
        """Convert \\n escape sequences to <br> tags for display"""
        if text is None:
            return ''
        # Convert string to str if needed
        text = str(text)
        # Replace literal \n with actual line breaks, then convert to HTML
        text = text.replace('\\n', '\n')
        # Split by newlines and join with <br> tags
        lines = text.split('\n')
        return Markup('<br>'.join(lines))
    
    app.jinja_env.filters['nl2br'] = nl2br_filter
    
    # CORS is opt-in: this is a same-origin monolith (templates + API served together),
    # so cross-origin credentialed requests are only enabled if an allowlist is configured.
    # (Previously CORS(app, supports_credentials=True) with no origins allowed any origin
    # to make credentialed requests, since flask-cors reflects the request Origin in that case.)
    allowed_origins = [o.strip() for o in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if o.strip()]
    if allowed_origins:
        CORS(app, supports_credentials=True, origins=allowed_origins)

    # Initialize session management
    Session(app)

    # Initialize rate limiter
    limiter.init_app(app)

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        """Flask-Limiter's default 429 is an HTML error page, which breaks any JSON-expecting
        fetch() caller (e.g. Ask AI) — response.json() throws, surfacing as a confusing
        generic "Request failed" message instead of a clear rate-limit notice."""
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Too many requests — please slow down and try again shortly.'}), 429
        return e

    # Initialize CSRF protection globally (all POST/PUT/PATCH/DELETE routes and forms)
    csrf = CSRFProtect(app)
    app.extensions['csrf'] = csrf

    # Initialize admin interface
    admin = init_admin(app)
    app.admin = admin
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(main_bp)
    
    # Add context processor to inject current_locale into all templates
    @app.context_processor
    def inject_locale():
        """Make current_locale available in all templates"""
        locale = get_locale()
        # Ensure it's always a string, not a Locale object
        locale_str = str(locale) if locale else 'en'
        return {'current_locale': locale_str}
    
    # Add template helper for content translation
    @app.context_processor
    def inject_translation_helpers():
        """Make translation helpers available in all templates"""
        from lms.content_translator import get_translated_content, get_translated_json_array
        
        def translate_field(content_type, content_id, field_name, original_text):
            """Get translated content based on current locale"""
            locale = get_locale()
            return get_translated_content(content_type, content_id, field_name, original_text, locale)
        
        def translate_json(content_type, content_id, field_name, json_array):
            """Get translated JSON array based on current locale"""
            locale = get_locale()
            return get_translated_json_array(content_type, content_id, field_name, json_array, locale)
        
        def get_localized_image(image_dict, fallback=''):
            """Get image URL based on current locale"""
            locale = str(get_locale()) if get_locale() else 'en'
            if isinstance(image_dict, dict):
                return image_dict.get(locale, image_dict.get('en', fallback))
            return fallback
        
        return {
            'translate_field': translate_field,
            'translate_json': translate_json,
            'get_localized_image': get_localized_image
        }
    
    import re

    @app.context_processor
    def inject_render_functions():
        """Make rendering functions available in templates"""
        import os
        from urllib.parse import urlparse, parse_qs

        def add_file_emoji(item):
            """Add emoji to file name based on extension or MIME type"""
            # Get filename from title or drive_view_link
            filename = getattr(item, 'title', '') or ''
            drive_file_id = getattr(item, 'drive_file_id', '') or ''
            drive_link = getattr(item, 'drive_view_link', '') or ''

            # Import URL parsing functions

            # Try to get MIME type from Google Drive API first (most reliable)
            mime_type = ''
            if drive_file_id:
                try:
                    from lms.google_drive_service import authenticate, get_file_metadata
                    from flask_login import current_user

                    # Only try API if user is authenticated with Google
                    if current_user and current_user.google_access_token:
                        service = authenticate(current_user)
                        if service:
                            metadata = get_file_metadata(service, drive_file_id)
                            if metadata and 'mimeType' in metadata:
                                mime_type = metadata['mimeType']
                except Exception:
                    pass

            # If we got MIME type, map it to extension
            ext = ''
            if mime_type:
                # MIME type to extension mapping
                mime_to_ext = {
                    # Images
                    'image/jpeg': '.jpg',
                    'image/png': '.png',
                    'image/gif': '.gif',
                    'image/svg+xml': '.svg',
                    'image/webp': '.webp',

                    # Videos
                    'video/mp4': '.mp4',
                    'video/quicktime': '.mov',
                    'video/x-msvideo': '.avi',
                    'video/webm': '.webm',

                    # Audio
                    'audio/mpeg': '.mp3',
                    'audio/wav': '.wav',
                    'audio/x-wav': '.wav',
                    'audio/mp4': '.m4a',

                    # Documents
                    'application/pdf': '.pdf',
                    'application/msword': '.doc',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                    'application/vnd.ms-powerpoint': '.ppt',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
                    'application/vnd.ms-excel': '.xls',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',

                    # Text/Data
                    'text/plain': '.txt',
                    'text/csv': '.csv',
                    'application/json': '.json',
                    'application/xml': '.xml',
                    'text/xml': '.xml',

                    # Adobe
                    'image/vnd.adobe.photoshop': '.psd',
                }
                ext = mime_to_ext.get(mime_type, '')

            # If no MIME type, fall back to URL parsing
            if not ext and drive_link:
                # Try to extract filename from URL parameters first (most reliable)
                try:
                    parsed_url = urlparse(drive_link)
                    query_params = parse_qs(parsed_url.query)
                    if 'filename' in query_params:
                        filename_param = query_params['filename'][0]
                        _, ext = os.path.splitext(filename_param.lower())
                except Exception:
                    pass

                # If no filename parameter, try extracting from URL path (avoid domain parts)
                if not ext:
                    try:
                        parsed = urlparse(drive_link)
                        path_parts = parsed.path.split('/')
                        for part in reversed(path_parts):
                            if '.' in part and len(part.split('.')[-1]) <= 4:  # Reasonable extension length
                                # Remove query parameters
                                filename_from_url = part.split('?')[0]
                                _, ext = os.path.splitext(filename_from_url.lower())
                                break
                    except Exception:
                        pass

            # If no extension from URL, try title
            if not ext and filename:
                try:
                    _, ext = os.path.splitext(filename.lower())
                except Exception:
                    # Fallback: extract extension manually
                    parts = filename.lower().rsplit('.', 1)
                    if len(parts) == 2:
                        ext = '.' + parts[1]

            _b = '/static/permanent/file%20type%20icons'
            icon_map = {
                '.mp3': f'{_b}/mp3%20file%20icon.png',
                '.wav': f'{_b}/wav%20file%20icon.png',
                '.m4a': f'{_b}/mp3%20file%20icon.png',
                '.mp4': f'{_b}/mov%20file%20icon.png',
                '.mov': f'{_b}/mov%20file%20icon.png',
                '.avi': f'{_b}/mov%20file%20icon.png',
                '.webm': f'{_b}/mov%20file%20icon.png',
                '.txt': f'{_b}/txt%20file%20icon.png',
                '.pdf': f'{_b}/pdf%20file%20icon.png',
                '.doc': f'{_b}/doc%28x%29%20file%20icon.png',
                '.docx': f'{_b}/doc%28x%29%20file%20icon.png',
                '.ppt': f'{_b}/ppt%20file%20icon.png',
                '.pptx': f'{_b}/ppt%20file%20icon.png',
                '.jpg': f'{_b}/jpg%20file%20icon.png',
                '.jpeg': f'{_b}/jpg%20file%20icon.png',
                '.png': f'{_b}/png%20file%20icon.png',
                '.svg': f'{_b}/png%20file%20icon.png',
                '.webp': f'{_b}/jpg%20file%20icon.png',
                '.gif': f'{_b}/jpg%20file%20icon.png',
                '.rar': f'{_b}/rar%20file%20icon.png',
                '.zip': f'{_b}/zip%20file%20icon.png',
            }

            icon_url = icon_map.get(ext, '')
            if icon_url:
                return f'<img src="{icon_url}" style="height:45px;width:auto;vertical-align:middle;margin-left:8px;" alt="">'
            return ''

        return {
            're': re,
            'add_file_emoji': add_file_emoji,
        }

    return app

