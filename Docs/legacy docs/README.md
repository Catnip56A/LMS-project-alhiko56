# LMS - Learning Platform

A comprehensive learning management platform built with Python Flask, featuring user authentication, course management, resource sharing, community forums, Google Drive integration, and administrative tools.

## 🚀 Features

### Core Functionality
- **User Authentication**: Secure login/logout with admin and teacher roles
- **Course Management**: Enroll in and manage learning courses with content modules, assignments, and announcements
- **Resource Library**: Upload and access protected learning materials with Google Drive integration
- **PDF Document Management**: Secure PDF upload and access with PIN protection
- **Community Forum**: Interactive discussion forum with threaded replies and channel-based organization
- **Course Content Management**: Organize course materials in folders with assignments and submissions
- **Google Drive Integration**: Seamless file storage and sharing via Google Drive
- **Background Job Processing**: Asynchronous task processing for translations and file operations
- **Admin Dashboard**: Comprehensive administrative interface for system management

### Technical Features
- **Multi-language Support**: English, Azerbaijani, and Russian language options
- **Responsive Design**: Mobile-friendly web interface
- **RESTful API**: JSON-based API for frontend integration
- **Secure File Uploads**: Protected resource and PDF management with Google Drive
- **Session Management**: Secure user sessions with Flask-Login
- **Database**: PostgreSQL with SQLAlchemy ORM and migration support
- **Internationalization**: Dynamic content translation with AI-powered services
- **Forum Channels**: Multi-channel forum with tiered access control (public/login-required/admin-only)

## 🛠️ Technology Stack

- **Backend**: Python Flask
- **Database**: PostgreSQL with SQLAlchemy
- **Authentication**: Flask-Login with Google OAuth
- **Admin Interface**: Flask-Admin
- **Internationalization**: Flask-Babel with AI translation
- **File Storage**: Google Drive API integration
- **Job Processing**: Custom background job system
- **Frontend**: HTML5, CSS3, JavaScript (ES6+)
- **Styling**: Custom responsive CSS
- **Deployment**: Gunicorn + Caddy web server

## 📋 Prerequisites

- Python 3.8+
- PostgreSQL database
- Google Cloud Project with Drive API enabled
- pip package manager

## 🚀 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd LMS
   ```

2. **Create virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   Create a `.env` file with:
   ```env
   FLASK_ENV=development
   SECRET_KEY=your-super-secret-key-change-this-make-it-long-and-random
   DATABASE_URL=postgresql://username:password@localhost:5432/lms_db
   GOOGLE_CLIENT_ID=your-google-client-id
   GOOGLE_CLIENT_SECRET=your-google-client-secret
   ```

5. **Set up Google Drive integration**:
   - Place your Google service account JSON file in the project root
   - Update the filename in `config.py` if different

6. **Initialize the database**:
   ```bash
   flask db upgrade
   ```

7. **Create admin user** (optional):
   ```bash
   python create_admin.py
   ```

8. **Run the application**:
   ```bash
   python app.py
   ```

8. **Access the application**:
   - Main site: http://localhost:5000
   - Admin dashboard: http://localhost:5000/admin (admin login required)

## 📁 Project Structure

```
lms/
├── __init__.py              # Flask application factory
├── config.py                # Application configuration
├── models/
│   └── __init__.py          # Database models (User, Course, etc.)
├── routes/
│   ├── api.py               # REST API endpoints
│   ├── auth.py              # Authentication routes
│   └── __init__.py          # Main web routes
├── admin/
│   └── __init__.py          # Admin interface configuration
├── templates/               # Jinja2 templates
├── translations/            # Internationalization files
│   ├── az/                  # Azerbaijani translations
│   ├── en/                  # English translations
│   └── ru/                  # Russian translations
├── content_translator.py    # Dynamic content translation system
├── google_drive_service.py  # Google Drive API integration
├── job_manager.py           # Background job processing
├── translation_service.py   # AI-powered translation services
└── babel.cfg                # Babel configuration

static/                      # Static assets (CSS, JS, images)
├── permanent/               # Permanent static files
└── uploads/                 # User uploaded files (via Google Drive)

Additional_scripts/          # Database management and utility scripts
├── create_admin.py          # Admin user creation
├── backup_db.sh             # Database backup script
├── restore_db.sh            # Database restore script
└── ...                      # Other utility scripts

migrations/                  # Database migrations
deploy/                      # Deployment configuration
└── Caddyfile                # Caddy web server configuration
```

## 🔧 Configuration

Key configuration options in `lms/config.py`:
- Database URI (PostgreSQL)
- Secret key for sessions
- Google OAuth credentials
- Session settings
- Language settings
- File upload limits

## 🌐 API Endpoints

### Authentication
- `POST /login` - User login
- `POST /logout` - User logout
- `GET /api/user` - Get current user info

### Courses
- `GET /api/courses` - Get available courses
- `POST /api/courses/{id}/enroll` - Enroll in course
- `GET /api/courses/{id}/content` - Get course content
- `POST /api/courses/{id}/assignments/{aid}/submit` - Submit assignment

### Resources
- `GET /api/resources` - Get learning resources
- `POST /api/resources` - Upload new resource
- `POST /api/resources/{id}/access` - Access protected resource

### PDFs
- `GET /api/pdfs` - Get PDF documents
- `POST /api/pdfs/upload` - Upload PDF document

### Forum
- `GET /api/forum/channels` - Get all forum channels
- `GET /api/forum/messages` - Get forum messages
- `POST /api/forum/messages` - Create new message
- `PUT /api/forum/messages/{id}` - Update message
- `DELETE /api/forum/messages/{id}` - Delete message

### Translations
- `POST /api/translate` - Request content translation
- `GET /api/translation/status/{job_id}` - Check translation status

## 🔒 Security Features

- Password hashing with Werkzeug
- Session-based authentication with Google OAuth
- Admin and teacher role-based access control
- PIN-protected resource access
- Secure file upload validation with Google Drive
- CSRF protection
- Rate limiting and account lockout
- Input validation and sanitization

## 🌍 Internationalization

The application supports multiple languages:
- English (en)
- Azerbaijani (az)
- Russian (ru)

Language files are located in `lms/translations/`. Content translation is handled dynamically using AI services.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For support or questions, please contact the development team or create an issue in the repository.

---

For detailed functionality documentation, see [FUNCTIONALITY.md](FUNCTIONALITY.md).
