"""
LMS Application Entry Point
"""
import os

# Load environment variables from .env file

from lms import create_app

app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Add CORS headers to allow Google Drive images and videos to load
@app.after_request
def add_cors_headers(response):
    """Add CORS headers to allow cross-origin requests for images and videos"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Headers'] = 'Range'
    response.headers['Accept-Ranges'] = 'bytes'
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

