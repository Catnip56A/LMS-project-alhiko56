import os
from dotenv import load_dotenv

# Load .env if present (no-op in Docker where compose injects env vars)
load_dotenv()

from yonca import create_app

app = create_app(os.environ.get('FLASK_ENV', 'production'))
