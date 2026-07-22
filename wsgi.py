import os

# Load .env if present (no-op in Docker where compose injects env vars)

from lms import create_app

app = create_app(os.environ.get('FLASK_ENV', 'production'))
