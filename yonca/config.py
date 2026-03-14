"""
Application configuration
"""
import os
import json

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL environment variable is not set")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'flask_session')
    SESSION_COOKIE_NAME = 'yonca_session'
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_HTTPONLY = False  # Allow JavaScript to see cookie for debugging
    SESSION_COOKIE_DOMAIN = None  # Works with localhost
    SESSION_COOKIE_PATH = '/'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour
    
    # Load Google OAuth credentials from JSON file
    google_creds_path = os.path.join(os.path.dirname(__file__), '..', 'client_secret_860511395930-3eojlbffavnl47upo580avedqa49lq3f.apps.googleusercontent.com.json')
    if os.path.exists(google_creds_path):
        with open(google_creds_path, 'r') as f:
            google_creds = json.load(f)
            GOOGLE_CLIENT_ID = google_creds['web']['client_id']
            GOOGLE_CLIENT_SECRET = google_creds['web']['client_secret']
    else:
        GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
        GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_TYPE = 'filesystem'
    SESSION_COOKIE_SECURE = True  # HTTPS required
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
