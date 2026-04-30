"""
Application factory and initialization
"""
from flask import Flask, request, redirect, url_for, jsonify
from flask_login import LoginManager
from flask_cors import CORS
from flask_session import Session
from flask_babel import Babel
from yonca.config import config
from yonca.models import db, User, Course, ForumMessage, ForumChannel, Resource, PDFDocument, TaviTest, HomeContent, Translation
from flask_migrate import Migrate
from yonca.admin import init_admin
from yonca.routes.auth import auth_bp
from yonca.routes.api import api_bp
from yonca.routes import main_bp
import os
import psycopg2
from urllib.parse import urlparse
import logging

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
            print(f"Database {db_name} created.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")

def create_app(config_name='development'):
    """Create and configure Flask application"""
    # Get the package directory
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(package_dir)
    static_dir = os.path.join(project_root, 'static')
    template_dir = os.path.join(package_dir, 'templates')
    
    app = Flask(__name__, static_folder=static_dir, static_url_path='/static', template_folder=template_dir)
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Create PostgreSQL database if it doesn't exist
    # if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI']:
    #     create_database_if_not_exists(app.config['SQLALCHEMY_DATABASE_URI'])
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.unauthorized_handler
    def unauthorized():
        """Handle unauthorized requests - return JSON for API, redirect for web"""
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required'}), 401
        return redirect(url_for('auth.login'))
    
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
        
        # Check URL parameter first
        lang = request.args.get('lang')
        if lang and lang in ['en', 'ru', 'az']:
            print(f"DEBUG: Babel get_locale from URL: {lang}")
            # If language is Azerbaijani, switch to English unless on privacy/terms pages
            if lang == 'az' and not _is_on_legal_page(request):
                print(f"DEBUG: Babel overriding Azerbaijani to English (not on legal page)")
                return 'en'
            return lang

        # Check if language is set in session
        lang = session.get('language')
        if lang and lang in ['en', 'ru', 'az']:
            print(f"DEBUG: Babel get_locale from session: {lang}")
            # If language is Azerbaijani, switch to English unless on privacy/terms pages
            if lang == 'az' and not _is_on_legal_page(request):
                print(f"DEBUG: Babel overriding Azerbaijani to English (not on legal page)")
                return 'en'
            return lang
        
        # Default to English
        print("DEBUG: Babel get_locale defaulting to English")
        return 'en'
    
    # Set locale selector using the correct attribute
    babel.init_app(app, locale_selector=get_locale)
    
    # Helper function to check if the current request is on a legal page (privacy/terms)
    def _is_on_legal_page(request):
        """Check if the current request path is for privacy policy or terms of use"""
        path = request.path.lower()
        return path in ['/privacy', '/privacy-policy', '/terms']
    
    # Add Babel's _ function to Jinja2 globals for template translations
    from flask_babel import gettext as _gettext
    app.jinja_env.globals['_'] = _gettext
    
    # Enable CORS with credentials support
    CORS(app, supports_credentials=True)
    
    # Initialize session management
    Session(app)
    
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
        print(f"DEBUG: inject_locale() returning: {locale_str} (original: {locale}, type: {type(locale)})")
        return {'current_locale': locale_str}
    
    # Add template helper for content translation
    @app.context_processor
    def inject_translation_helpers():
        """Make translation helpers available in all templates"""
        from yonca.content_translator import get_translated_content, get_translated_json_array
        
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
    
    # Add custom Jinja2 filter for button syntax in course descriptions
    import re
    from markupsafe import Markup
    
    # Make page builder rendering function available in all templates
    @app.context_processor
    def inject_render_functions():
        """Make rendering functions available in templates"""
        from yonca.page_builder_utils import render_page_builder_blocks
        import re
        import os
        from urllib.parse import urlparse, parse_qs

        def add_file_emoji(item):
            """Add emoji to file name based on extension or MIME type"""
            # Get filename from title or drive_view_link
            filename = getattr(item, 'title', '') or ''
            drive_file_id = getattr(item, 'drive_file_id', '') or ''
            drive_link = getattr(item, 'drive_view_link', '') or ''

            # Import URL parsing functions
            from urllib.parse import urlparse, parse_qs

            # Try to get MIME type from Google Drive API first (most reliable)
            mime_type = ''
            if drive_file_id:
                try:
                    from yonca.google_drive_service import authenticate, get_file_metadata
                    from flask_login import current_user

                    # Only try API if user is authenticated with Google
                    if current_user and current_user.google_access_token:
                        service = authenticate(current_user)
                        if service:
                            metadata = get_file_metadata(service, drive_file_id)
                            if metadata and 'mimeType' in metadata:
                                mime_type = metadata['mimeType']
                except Exception as e:
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
                except:
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
                    except:
                        pass

            # If no extension from URL, try title
            if not ext and filename:
                try:
                    _, ext = os.path.splitext(filename.lower())
                except:
                    # Fallback: extract extension manually
                    parts = filename.lower().rsplit('.', 1)
                    if len(parts) == 2:
                        ext = '.' + parts[1]

            # Emoji mappings based on file type
            emoji_map = {
                # Media files
                '.mp3': '🎧',
                '.wav': '🎧',
                '.m4a': '🎧',
                '.mp4': '🎥',
                '.mov': '🎥',
                '.avi': '🎥',
                '.webm': '🎥',

                # Documents & Text
                '.txt': '📝',
                '.pdf': '📕',
                '.doc': '📄',
                '.docx': '📄',
                '.ppt': '📊',
                '.pptx': '📊',
                '.xml': '🗒️',
                '.json': '🗒️',
                '.csv': '📗',
                '.xls': '📗',
                '.xlsx': '📗',

                # Images & Graphics
                '.jpg': '📷',
                '.jpeg': '📷',
                '.png': '📷',
                '.svg': '📷',
                '.webp': '📷',
                '.gif': '🎞️',
                '.psd': '🎨',
            }

            emoji = emoji_map.get(ext, '')
            return f"{filename} {emoji}".strip()

        return {
            'render_page_builder_blocks': render_page_builder_blocks,
            're': re,
            'add_file_emoji': add_file_emoji,
        }
    
    @app.template_filter('parse_buttons')
    def parse_buttons(text):
        """Convert <button: [text]> url </button> syntax to HTML buttons"""
        if not text:
            return text
        
        # Regex to match <button: [text]> url </button>
        pattern = r'<button:\s*\[([^\]]+)\]\s*>\s*([^<\s]+)\s*</button>'
        
        def replace_button(match):
            button_text = match.group(1).strip()
            url = match.group(2).strip()
            return f'<a href="{url}" target="_blank" class="btn btn-primary btn-sm me-2 mb-2">{button_text}</a>'
        
        # Replace all button syntax with HTML buttons
        result = re.sub(pattern, replace_button, text, flags=re.IGNORECASE)
        return Markup(result)
    
    # Start background job worker — skip during Flask CLI commands (migrations, shell, etc.)
    import sys
    is_cli = any(cmd in sys.argv for cmd in ('db', 'shell', 'routes', 'translate'))
    if not is_cli:
        from yonca.job_manager import job_manager
        job_manager.start_worker(app)
    
    return app

