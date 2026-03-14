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
    app.config['BABEL_DEFAULT_LOCALE'] = 'az'
    
    babel = Babel(app)
    
    def get_locale():
        """Select the language for the current request"""
        from flask import request, session
        
        # Check URL parameter first
        lang = request.args.get('lang')
        if lang and lang in ['en', 'az', 'ru']:
            print(f"DEBUG: Babel get_locale from URL: {lang}")
            return lang
        
        # Check if language is set in session
        lang = session.get('language')
        if lang and lang in ['en', 'az', 'ru']:
            print(f"DEBUG: Babel get_locale from session: {lang}")
            return lang
        
        # Default to Azerbaijani
        print("DEBUG: Babel get_locale defaulting to Azerbaijani")
        return 'az'
    
    # Set locale selector using the correct attribute
    babel.init_app(app, locale_selector=get_locale)
    
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
        return {
            'render_page_builder_blocks': render_page_builder_blocks,
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

