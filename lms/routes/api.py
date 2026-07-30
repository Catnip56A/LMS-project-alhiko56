"""
API routes for courses, forum, and resources
"""
import os
import re
import requests
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app, redirect, url_for, Response
from flask_login import current_user, login_required
from lms.extensions import limiter
from lms.models import Course, ForumMessage, ForumChannel, PDFDocument, Translation, db
from lms.translation_service import translation_service
from lms.google_drive_service import authenticate, create_view_only_link, set_file_permissions, import_drive_file, import_drive_folder
from lms.upload_validation import validate_upload, UploadValidationError, PDF_MIME_TYPES

api_bp = Blueprint('api', __name__, url_prefix='/api')

def api_unauthorized():
    """Return JSON 401 for API unauthorized requests"""
    return jsonify({'error': 'Authentication required'}), 401

def allowed_file(filename, allowed_extensions):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def is_image_file(filename):
    """Check if file is an image based on extension"""
    image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
    return allowed_file(filename, image_extensions)

# Set custom unauthorized handler for API blueprint
api_bp.unauthorized = api_unauthorized

@api_bp.route('/proxy-image/<file_id>')
def proxy_image(file_id):
    """
    Proxy Google Drive images to bypass CORB (Cross-Origin Read Blocking).
    
    Tries multiple endpoints:
    1. Drive thumbnail API (public, fast)
    2. Export as image endpoint
    
    Args:
        file_id: Google Drive file ID
    
    Returns:
        The image with proper content-type headers
    """
    # Validate file_id format to prevent injection attacks
    if not re.match(r'^[a-zA-Z0-9_\-]+$', file_id):
        current_app.logger.warning(f"Invalid file ID format: {file_id}")
        return jsonify({'error': 'Invalid file ID format'}), 400
    
    try:
        current_app.logger.info(f"Proxying image request for file_id: {file_id}")
        
        # Browser-like headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://drive.google.com/',
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'
        }
        
        # Try multiple Google Drive image endpoints in order of preference
        urls_to_try = [
            # 1. Thumbnail API (public, no auth needed)
            f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000",
            # 2. Export with preview=true parameter
            f"https://drive.google.com/uc?export=view&id={file_id}",
            # 3. Open endpoint
            f"https://drive.google.com/open?id={file_id}",
        ]
        
        response = None
        for url in urls_to_try:
            try:
                current_app.logger.info(f"Trying URL: {url}")
                resp = requests.get(url, timeout=15, allow_redirects=True, headers=headers, stream=False)
                
                if resp.status_code == 200 and resp.headers.get('Content-Type', '').startswith('image'):
                    response = resp
                    current_app.logger.info(f"Success with {url}: {resp.headers.get('Content-Type')}")
                    break
                else:
                    current_app.logger.warning(f"Failed {url}: status={resp.status_code}, content-type={resp.headers.get('Content-Type')}")
            except Exception as e:
                current_app.logger.warning(f"Error trying {url}: {str(e)}")
                continue
        
        if not response:
            current_app.logger.error(f"All endpoints failed for file {file_id}")
            return jsonify({'error': 'File not found or not publicly shared'}), 404
        
        # Return the image with proper headers
        return Response(
            response.content,
            mimetype=response.headers.get('Content-Type', 'image/jpeg'),
            headers={
                'Cache-Control': 'public, max-age=31536000',
                'Content-Type': response.headers.get('Content-Type', 'image/jpeg')
            }
        )
    except requests.exceptions.Timeout:
        current_app.logger.error(f"Timeout fetching image {file_id}")
        return jsonify({'error': 'Request timeout'}), 504
    except Exception as e:
        current_app.logger.error(f"Error proxying image {file_id}: {type(e).__name__}: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': 'Failed to fetch image'}), 500

@api_bp.route('/courses')
def get_courses():
    """Get all courses with enrollment status for authenticated users"""
    from flask import session, request
    from lms.content_translator import get_translated_content, get_translated_string_array

    # Get language from query parameter, or fall back to session language
    user_locale = request.args.get('lang', session.get('language', 'en'))

    if current_user.is_authenticated:
        # Get all courses
        all_courses = Course.query.all()
        # Get user's enrolled course IDs
        enrolled_course_ids = {course.id for course in current_user.courses}

        return jsonify([{
            'id': c.id,
            'title': get_translated_content('course', c.id, 'title', c.title, user_locale),
            'description': get_translated_content('course', c.id, 'description', c.description, user_locale),
            'time_slot': c.time_slot,
            'tags': get_translated_string_array('course', c.id, 'tags', c.tags, user_locale),
            'is_enrolled': c.id in enrolled_course_ids
        } for c in all_courses])
    else:
        # For non-authenticated users, return all courses without enrollment status
        courses = Course.query.all()

        return jsonify([{
            'id': c.id,
            'title': get_translated_content('course', c.id, 'title', c.title, user_locale),
            'description': get_translated_content('course', c.id, 'description', c.description, user_locale),
            'time_slot': c.time_slot,
            'tags': get_translated_string_array('course', c.id, 'tags', c.tags, user_locale)
        } for c in courses])

@api_bp.route('/user')
def get_current_user():
    """Get current user information"""
    from flask import session
    from lms.content_translator import get_translated_content, get_translated_string_array
    
    # Get user's current locale
    user_locale = session.get('language', 'en')
    
    if current_user.is_authenticated:
        return jsonify({
            'id': current_user.id,
            'username': current_user.username,
            'email': current_user.email,
            'is_admin': current_user.is_admin,
            'preferred_language': current_user.preferred_language,
            'courses': [{
                'id': c.id,
                'title': get_translated_content('course', c.id, 'title', c.title, user_locale),
                'description': get_translated_content('course', c.id, 'description', c.description, user_locale),
                'time_slot': c.time_slot,
                'tags': get_translated_string_array('course', c.id, 'tags', c.tags, user_locale)
            } for c in current_user.courses]
        })
    else:
        return jsonify(None)


@api_bp.route('/forum/channels')
def get_forum_channels():
    """Get all active forum channels.

    Guests (not authenticated) only see channels marked is_public — a discoverability
    filter layered on top of requires_login/admin_only, which still gate actual message
    access below. Authenticated users see every active channel, same as before.
    """
    query = ForumChannel.query.filter_by(is_active=True)
    if not current_user.is_authenticated:
        query = query.filter_by(is_public=True)
    channels = query.order_by(ForumChannel.sort_order).all()

    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'description': c.description,
        'requires_login': c.requires_login,
        'admin_only': c.admin_only,
        'is_public': c.is_public
    } for c in channels])

@api_bp.route('/forum/messages')
def get_forum_messages():
    """Get forum messages, optionally filtered by channel"""
    channel_slug = request.args.get('channel', 'general')

    # Get channel from database
    channel = ForumChannel.query.filter_by(slug=channel_slug, is_active=True).first()
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    # Check access permissions
    if channel.admin_only:
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': 'Admin access required for this channel'}), 403
    elif channel.requires_login and not current_user.is_authenticated:
        return jsonify({'error': 'Authentication required for this channel'}), 403
    
    def build_thread(message, depth=0):
        """Recursively build message thread"""
        # Get user's preferred language
        user_language = current_user.preferred_language if current_user.is_authenticated else 'en'

        result = {
            'id': message.id,
            'username': message.username,
            'message': message.message,
            'timestamp': message.timestamp.isoformat(),
            'channel': message.channel,
            'is_current_user': current_user.is_authenticated and message.username == current_user.username,
            'depth': depth,
            'user_language': user_language,
            'replies': []
        }

        # Get replies sorted by timestamp
        for reply in message.replies.order_by(ForumMessage.timestamp.asc()).all():
            result['replies'].append(build_thread(reply, depth + 1))

        return result
    
    # Get messages for the specified channel
    top_level_messages = ForumMessage.query.filter_by(channel=channel_slug, parent_id=None).order_by(ForumMessage.timestamp.desc()).all()
    
    return jsonify({
        'channel': channel_slug,
        'channel_name': channel.name,
        'requires_login': channel.requires_login,
        'messages': [build_thread(msg) for msg in top_level_messages]
    })

@api_bp.route('/forum/messages', methods=['POST'])
def post_forum_message():
    """Post a new forum message or reply"""
    data = request.get_json()

    if not data or 'message' not in data:
        return jsonify({'error': 'Message required'}), 400
    
    channel = data.get('channel', 'general')
    
    # Validate channel exists and is active
    channel_obj = ForumChannel.query.filter_by(slug=channel, is_active=True).first()
    if not channel_obj:
        return jsonify({'error': 'Channel not found'}), 404
    
    # Check access permissions
    if channel_obj.admin_only:
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': 'Admin access required for this channel'}), 403
    elif channel_obj.requires_login:
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required for this channel'}), 403
    
    parent_id = data.get('parent_id')
    if parent_id:
        # Verify parent message exists and is in the same channel
        parent = ForumMessage.query.filter_by(id=parent_id, channel=channel).first()
        if not parent:
            return jsonify({'error': 'Parent message not found in this channel'}), 404
    
    # Handle anonymous posting for public channels
    if not current_user.is_authenticated:
        # For anonymous users, require username
        username = data.get('username', '').strip()
        if not username:
            return jsonify({'error': 'Username required for anonymous posting'}), 400
        
        new_message = ForumMessage(
            username=username,
            message=data['message'],
            parent_id=parent_id,
            channel=channel
        )
    else:
        # Use the logged-in user's information
        new_message = ForumMessage(
            user_id=current_user.id,
            username=current_user.username,
            message=data['message'],
            parent_id=parent_id,
            channel=channel
        )
    
    db.session.add(new_message)
    db.session.commit()
    
    # Refresh to get the server-generated timestamp
    db.session.refresh(new_message)
    
    return jsonify({
        'success': True,
        'message_id': new_message.id,
        'message': new_message.message,
        'username': new_message.username,
        'channel': new_message.channel,
        'timestamp': new_message.timestamp.isoformat() if new_message.timestamp else None,
        'parent_id': new_message.parent_id
    }), 201
    
@api_bp.route('/forum/messages/<int:message_id>', methods=['PUT'])
@login_required
def edit_forum_message(message_id):
    """Edit a forum message (only by owner or admin)"""
    message = ForumMessage.query.get_or_404(message_id)
    
    # Check if user owns the message or is admin
    if message.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'Message required'}), 400
    
    message.message = data['message']
    db.session.commit()
    
    return jsonify({'success': True}), 200

@api_bp.route('/forum/messages/<int:message_id>', methods=['DELETE'])
@login_required
def delete_forum_message(message_id):
    """Delete a forum message (only by owner or admin)"""
    message = ForumMessage.query.get_or_404(message_id)
    
    # Check if user owns the message or is admin
    if message.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(message)
    db.session.commit()
    
    return jsonify({'success': True}), 200

@api_bp.route('/pdfs')
def get_pdfs():
    """Get all active PDF documents (without sensitive info)"""
    from flask_login import current_user
    pdfs = PDFDocument.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'description': p.description,
        'file_size': p.file_size,
        'upload_date': p.upload_date.isoformat() if p.upload_date else None,
        'uploaded_by': p.uploaded_by,
        # Only show PIN to the uploader
        'access_pin': p.access_pin if (current_user.is_authenticated and p.uploaded_by == current_user.id) else None
    } for p in pdfs])

@api_bp.route('/pdfs/upload', methods=['POST'])
@limiter.limit("5 per 30 seconds")
def upload_pdf():
    """Upload a new PDF document"""
    from flask import request
    import random
    import string
    from flask_login import current_user
    
    # Check if user is authenticated and is admin
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    # Check if user has Google OAuth tokens
    if not current_user.google_access_token:
        return jsonify({
            'error': 'Google Drive access required. Please link your Google account first.',
            'login_required': True,
            'login_url': url_for('auth.link_google_account', _external=True)
        }), 403
    
    # Check if file is present
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Only PDF files are allowed'}), 400

    try:
        validate_upload(file, max_bytes=current_app.config['MAX_CONTENT_LENGTH'], expected_mimes=PDF_MIME_TYPES)
    except UploadValidationError as e:
        return jsonify({'error': str(e)}), 400

    # Get form data
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    pin = request.form.get('pin', '').strip()
    
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    # Generate PIN if not provided
    if not pin:
        pin = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Validate PIN length
    if len(pin) < 4 or len(pin) > 10:
        return jsonify({'error': 'PIN must be 4-10 characters'}), 400
    
    try:
        # Create temporary directory
        temp_dir = os.path.join(current_app.static_folder, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Generate secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{random.randint(1000, 9999)}_{filename}"
        temp_file_path = os.path.join(temp_dir, unique_filename)
        
        # Save file temporarily
        file.save(temp_file_path)
        
        # Upload to Google Drive
        from lms.google_drive_service import authenticate, upload_file, create_view_only_link
        service = authenticate()
        if not service:
            return jsonify({'error': 'Failed to authenticate with Google Drive'}), 500
        
        try:
            drive_file_id = upload_file(service, temp_file_path, filename)
        except Exception as e:
            current_app.logger.error(f"Error uploading to Drive: {e}")
            if "insufficientPermissions" in str(e) or "403" in str(e):
                return jsonify({'error': 'Your Google account does not have sufficient permissions. Please re-link your Google account with full Drive access.'}), 403
            return jsonify({'error': 'Failed to upload file to Google Drive'}), 500
        
        if not drive_file_id:
            return jsonify({'error': 'Failed to upload file to Google Drive'}), 500
        
        # Create view-only link
        view_link = create_view_only_link(service, drive_file_id, is_image=False)
        if not view_link:
            return jsonify({'error': 'Failed to create view link'}), 500
        
        # Create database record
        new_pdf = PDFDocument(
            title=title,
            description=description,
            filename=unique_filename,
            original_filename=file.filename,
            drive_file_id=drive_file_id,
            drive_view_link=view_link,
            file_size=os.path.getsize(temp_file_path),
            access_pin=pin,
            uploaded_by=current_user.id if current_user.is_authenticated else None
        )
        
        db.session.add(new_pdf)
        db.session.commit()
        
        # Clean up temporary file
        try:
            os.remove(temp_file_path)
        except Exception:
            pass
        
        return jsonify({
            'success': True,
            'id': new_pdf.id,
            'title': new_pdf.title,
            'pin': new_pdf.access_pin,
            'message': 'PDF uploaded successfully'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        # Clean up temporary file if it was saved
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

# Translation endpoints
@api_bp.route('/translate', methods=['POST'])
@limiter.limit("5 per 30 seconds")
def translate_text():
    """Translate text using AI translation service"""
    data = request.get_json()

    if not data or 'text' not in data:
        return jsonify({'error': 'Text is required'}), 400

    text = data['text']
    target_language = data.get('target_language', 'en')
    source_language = data.get('source_language', 'auto')
    return_all = data.get('return_all', False)

    if not text or not text.strip():
        return jsonify({'translated_text': text})

    try:
        # Always call get_translation to ensure all translations are cached
        translated_text = translation_service.get_translation(text, target_language, source_language)
        
        if return_all:
            # Return translations for all supported languages
            all_translations = {}
            detected_source = translation_service._detect_source_language(text)
            
            for lang in translation_service.SUPPORTED_LANGUAGES:
                if lang == detected_source:
                    all_translations[lang] = text
                else:
                    # Try to get from cache
                    cached = Translation.query.filter_by(
                        source_text=text,
                        target_language=lang,
                        source_language='auto'
                    ).first()
                    if cached:
                        all_translations[lang] = cached.translated_text
                    else:
                        all_translations[lang] = text  # Fallback to original
            
            return jsonify({
                'original_text': text,
                'detected_source_language': detected_source,
                'translations': all_translations,
                'requested_translation': {
                    'text': translated_text,
                    'target_language': target_language
                }
            })
        else:
            return jsonify({
                'original_text': text,
                'translated_text': translated_text,
                'target_language': target_language,
                'source_language': source_language
            })
    except Exception as e:
        current_app.logger.error(f"Translation API error: {str(e)}")
        return jsonify({'error': 'Translation failed', 'translated_text': text}), 500

@api_bp.route('/translate/content', methods=['POST'])
@limiter.limit("5 per 30 seconds")
def translate_content_field():
    """Translate a specific content field and save to ContentTranslation table."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    text = (data.get('text') or '').strip()
    content_type = data.get('content_type', 'site_settings')
    content_id = data.get('content_id')
    field_name = data.get('field_name')

    if not text or not content_id or not field_name:
        return jsonify({'error': 'text, content_id and field_name are required'}), 400

    try:
        from lms.content_translator import translate_content
        from lms.models import db
        saved = translate_content(content_type, int(content_id), field_name, text)
        if not saved:
            return jsonify({'error': 'Translation service unavailable. Check DEEPL_API_KEY is set in .env'}), 503
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Content translation error: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/translate/batch', methods=['POST'])
@limiter.limit("5 per 30 seconds")
def translate_batch():
    """Translate multiple texts in batch"""
    data = request.get_json()

    if not data or 'texts' not in data:
        return jsonify({'error': 'Texts array is required'}), 400

    texts = data['texts']
    target_language = data.get('target_language', 'en')
    source_language = data.get('source_language', 'auto')

    if not isinstance(texts, list):
        return jsonify({'error': 'Texts must be an array'}), 400

    try:
        translations = []
        for text in texts:
            if text and text.strip():
                translated = translation_service.get_translation(text, target_language, source_language)
                translations.append({
                    'original': text,
                    'translated': translated
                })
            else:
                translations.append({
                    'original': text,
                    'translated': text
                })

        return jsonify({
            'translations': translations,
            'target_language': target_language,
            'source_language': source_language
        })
    except Exception as e:
        current_app.logger.error(f"Batch translation API error: {str(e)}")
        return jsonify({'error': 'Batch translation failed'}), 500

@api_bp.route('/languages')
def get_supported_languages():
    """Get list of supported languages for translation"""
    return jsonify(translation_service.get_supported_languages())


@api_bp.route('/content/view', methods=['POST'])
@login_required
def track_content_view():
    """Track user viewing of content and record viewing duration.

    Accepts both JSON (application/json) and URLSearchParams (application/x-www-form-urlencoded)
    payloads so that navigator.sendBeacon works reliably across all browsers.
    """
    from lms.models import ContentView, db

    # sendBeacon with URLSearchParams sends form-urlencoded; JSON browser sends application/json
    data = request.get_json(silent=True) or request.form

    content_type = data.get('content_type')
    content_id   = data.get('content_id')
    viewing_duration = data.get('viewing_duration', 0)

    if not content_type or not content_id:
        return jsonify({'error': 'Content type and content ID are required'}), 400

    user_id = current_user.id if current_user.is_authenticated else None
    if user_id is None:
        return jsonify({'success': True}), 200

    try:
        # Create a new content view record
        content_view = ContentView(
            user_id=user_id,
            content_type=content_type,
            content_id=content_id,
            viewing_duration=int(viewing_duration)
        )
        
        db.session.add(content_view)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'View tracking data recorded successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error tracking content view: {str(e)}")
        return jsonify({'error': 'Failed to record view tracking data'}), 500

@api_bp.route('/user/language', methods=['POST'])
@login_required
def set_user_language():
    """Set user's preferred language for translations"""
    data = request.get_json()

    if not data or 'language' not in data:
        return jsonify({'error': 'Language is required'}), 400

    language = data['language']
    supported_languages = translation_service.get_supported_languages()

    if language not in supported_languages:
        return jsonify({'error': 'Unsupported language'}), 400

    current_user.preferred_language = language
    db.session.commit()

    return jsonify({
        'success': True,
        'preferred_language': current_user.preferred_language
    })

@api_bp.route('/file/<file_id>')
@login_required
def serve_file(file_id):
    """Serve a Google Drive file after authentication"""
    from lms.models import CourseAssignmentSubmission, CourseContent, PDFDocument, Course
    from flask_login import current_user
    from flask import redirect, render_template, url_for

    # Find the file in any of the models that store files
    submission = CourseAssignmentSubmission.query.filter_by(drive_file_id=file_id).first()
    course_content = CourseContent.query.filter_by(drive_file_id=file_id).first()
    pdf_doc = PDFDocument.query.filter_by(drive_file_id=file_id).first()

    file_record = submission or course_content or pdf_doc

    if not file_record:
        return redirect(url_for('main.index', error='file_not_found'))

    # Resolve the course this file belongs to, if any, for course-scoped manager rights
    resolved_course = None
    if course_content:
        resolved_course = Course.query.get(course_content.course_id)
    elif submission and submission.assignment:
        resolved_course = submission.assignment.course

    # Determine ownership and permissions
    is_owner = False
    is_admin = current_user.is_authenticated and current_user.is_admin
    is_manager = resolved_course.is_managed_by(current_user) if resolved_course else False
    is_public = getattr(file_record, 'allow_others_to_view', True)  # Default to True if field doesn't exist

    # Check ownership based on file type
    if hasattr(file_record, 'user_id'):
        is_owner = current_user.is_authenticated and file_record.user_id == current_user.id
    elif hasattr(file_record, 'uploaded_by'):
        is_owner = current_user.is_authenticated and file_record.uploaded_by == current_user.id

    # Permission logic:
    # 1. Owner, admin, and the course's manager (teacher/creator) always have access
    # 2. For private files (allow_others_to_view=False), only owner/admin/manager can access
    # 3. For public files, enrolled students (for course content) or anyone can access

    if not is_public:
        if not (is_owner or is_admin or is_manager):
            return redirect(url_for('main.index', error='auth_required'))
    else:
        # For public course content, check enrollment
        if course_content:
            if current_user.is_authenticated:
                is_enrolled = resolved_course and current_user in resolved_course.users

                if not (is_owner or is_admin or is_manager or is_enrolled):
                    return redirect(url_for('main.index', error='auth_required'))
            else:
                return redirect(url_for('main.index', error='auth_required'))
    
    # For course content files, use the embedded viewer (no download)
    if course_content:
        file_title = course_content.title
        back_url = url_for('main.course_page_enrolled', course_id=course_content.course_id)
        
        # Detect file type from title/extension
        file_type = 'document'  # default
        if file_title:
            title_lower = file_title.lower()
            if any(ext in title_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']):
                file_type = 'image'
            elif any(ext in title_lower for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.aac']):
                file_type = 'audio'
            elif any(ext in title_lower for ext in ['.mp4', '.webm', '.ogv', '.mov', '.avi']):
                file_type = 'video'
            elif any(ext in title_lower for ext in ['.zip', '.rar', '.7z', '.tar', '.gz']):
                file_type = 'unsupported'
        
        return render_template('file_viewer.html',
                              content_id=course_content.id,
                              file_title=file_title,
                              file_type=file_type,
                              back_url=back_url,
                              current_user=current_user)

    
    # For other files (submissions, PDFs, etc.), redirect to the drive_view_link
    if hasattr(file_record, 'drive_view_link') and file_record.drive_view_link:
        return redirect(file_record.drive_view_link)
    
    # If no view link exists, try to construct a direct Google Drive link
    return redirect(f'https://drive.google.com/file/d/{file_id}/view')


@api_bp.route('/file/c/<int:content_id>')
@login_required
def serve_content_by_db_id(content_id):
    """Serve course content by its database ID, hiding the Drive file ID from clients."""
    from lms.models import CourseContent, Course
    from flask import render_template, redirect, url_for

    content = CourseContent.query.get(content_id)
    if not content:
        return redirect(url_for('main.index', error='file_not_found'))

    course = Course.query.get(content.course_id)
    is_manager = course.is_managed_by(current_user) if course else False
    is_enrolled = course and current_user in course.users
    if not (is_manager or is_enrolled):
        return redirect(url_for('main.index', error='auth_required'))
    if not content.is_published and not is_manager:
        return redirect(url_for('main.index', error='auth_required'))

    if content.content_type == 'file' and content.drive_file_id:
        file_title = content.title
        back_url = url_for('main.course_page_enrolled', course_id=content.course_id)
        file_type = 'document'
        title_lower = file_title.lower()
        if any(ext in title_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']):
            file_type = 'image'
        elif any(ext in title_lower for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.aac']):
            file_type = 'audio'
        elif any(ext in title_lower for ext in ['.mp4', '.webm', '.ogv', '.mov', '.avi']):
            file_type = 'video'
        elif any(ext in title_lower for ext in ['.zip', '.rar', '.7z', '.tar', '.gz']):
            file_type = 'unsupported'
        return render_template('file_viewer.html',
                               content_id=content_id,
                               file_title=file_title,
                               file_type=file_type,
                               back_url=back_url,
                               current_user=current_user)

    if content.drive_view_link:
        return redirect(content.drive_view_link)
    if content.content_data and content.content_data.startswith('http'):
        return redirect(content.content_data)
    return redirect(url_for('main.index', error='file_not_found'))


@api_bp.route('/file/c/<int:content_id>/embed')
@login_required
def serve_content_embed(content_id):
    """Redirect to the Drive embed URL without exposing the Drive file ID in page HTML."""
    from lms.models import CourseContent, Course
    from flask import redirect, abort

    content = CourseContent.query.get(content_id)
    if not content or not content.drive_file_id:
        abort(404)

    course = Course.query.get(content.course_id)
    is_manager = course.is_managed_by(current_user) if course else False
    is_enrolled = course and current_user in course.users
    if not (is_manager or is_enrolled):
        abort(403)
    if not content.is_published and not is_manager:
        abort(403)

    file_id = content.drive_file_id
    title_lower = (content.title or '').lower()
    if any(ext in title_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']):
        return redirect(f'https://lh3.googleusercontent.com/d/{file_id}')
    if any(ext in title_lower for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.aac']):
        return redirect(f'https://drive.google.com/uc?export=view&id={file_id}')
    return redirect(f'https://drive.google.com/file/d/{file_id}/preview')


@api_bp.route('/file/c/<int:content_id>/download')
@login_required
def download_content_by_db_id(content_id):
    """Download course content as a file attachment (only if is_downloadable is set)."""
    from lms.models import CourseContent, Course

    content = CourseContent.query.get(content_id)
    if not content:
        return redirect(url_for('main.index', error='file_not_found'))

    if not content.is_downloadable:
        return redirect(url_for('main.index', error='download_not_allowed'))

    course = Course.query.get(content.course_id)
    is_manager = course.is_managed_by(current_user) if course else False
    is_enrolled = course and current_user in course.users
    if not (is_manager or is_enrolled):
        return redirect(url_for('main.index', error='auth_required'))
    if not content.is_published and not is_manager:
        return redirect(url_for('main.index', error='auth_required'))

    if content.drive_file_id:
        return redirect(f'https://drive.google.com/uc?export=download&id={content.drive_file_id}')

    return redirect(url_for('main.index', error='file_not_found'))


@api_bp.route('/drive-picker-token')
@login_required
def get_drive_picker_token():
    """Return a valid (refreshed if needed) Drive access token for initialising the Google Picker."""
    from datetime import datetime
    from lms.google_drive_service import refresh_credentials

    # No course-scoped gate here — this just vends the caller's own Drive OAuth token
    # (drive.file scope, so it only ever grants access to files they create/pick
    # themselves). The actual privileged action (writing into a specific course) is
    # gated separately at picker_import() below.
    if not current_user.google_access_token:
        return jsonify({'error': 'no_token', 'message': 'Google account not linked'}), 401

    if current_user.google_token_expiry and datetime.utcnow() >= current_user.google_token_expiry:
        creds = refresh_credentials(current_user)
        if not creds:
            return jsonify({'error': 'refresh_failed', 'message': 'Token refresh failed — please re-link your Google account'}), 401

    return jsonify({'access_token': current_user.google_access_token}), 200


def _import_drive_tree(service, structure, course_id, parent_folder_id, published, allow_view, order_ref):
    """Recursively mirror a Drive folder tree into CourseContentFolder / CourseContent rows.

    order_ref is a one-element list [int] used as a mutable counter shared across calls.
    Returns the total number of file rows created.
    """
    from lms.models import CourseContent, CourseContentFolder
    from lms.google_drive_service import import_drive_file as _import_file

    created = 0

    for folder_info in structure.get('folders', []):
        cf = CourseContentFolder(
            course_id=course_id,
            parent_folder_id=parent_folder_id,
            title=folder_info['name'],
            order=order_ref[0],
        )
        db.session.add(cf)
        db.session.flush()
        order_ref[0] += 1
        created += _import_drive_tree(service, folder_info['structure'], course_id, cf.id, published, allow_view, order_ref)

    for file_info in structure.get('files', []):
        file_data = _import_file(service, file_info['id'])
        if not file_data or (isinstance(file_data, dict) and 'error' in file_data):
            continue
        view_link = file_data.get('view_link') or file_data.get('web_view_link', '')
        item = CourseContent(
            course_id=course_id,
            title=file_data.get('name', file_info['name']),
            description='',
            content_type='file',
            content_data=view_link,
            drive_file_id=file_data.get('file_id'),
            drive_view_link=view_link,
            order=order_ref[0],
            folder_id=parent_folder_id,
            is_published=published,
            allow_others_to_view=allow_view,
            is_imported=True,
        )
        db.session.add(item)
        order_ref[0] += 1
        created += 1

    return created


@api_bp.route('/picker-import', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def picker_import():
    """
    Import a single file that the teacher selected via the Google Picker.

    Calls files().get() to verify access, then permissions().create(type='anyone', role='reader')
    to make the file embeddable, and finally persists a CourseContent row.
    """
    from lms.models import CourseContent, CourseContentFolder, Course
    from lms.google_drive_service import (
        get_file_metadata,
    )

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    course_id = data.get('course_id')
    file_id = data.get('file_id', '').strip()
    file_name = data.get('file_name', '').strip()
    mime_type = data.get('mime_type', '')
    resource_key = data.get('resource_key', '').strip()
    folder_id = data.get('folder_id') or None
    title = data.get('title', '').strip() or file_name
    published = bool(data.get('published', True))
    allow_view = bool(data.get('allow_view', True))

    if not course_id or not file_id:
        return jsonify({'error': 'course_id and file_id are required'}), 400

    course = Course.query.get(int(course_id))
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    if not course.is_managed_by(current_user):
        return jsonify({'error': 'forbidden'}), 403

    service = authenticate(current_user)
    if not service:
        return jsonify({'error': 'no_token', 'message': 'Please link your Google account first'}), 401

    try:
        if mime_type == 'application/vnd.google-apps.folder':
            from lms.google_drive_service import collect_folder_structure, get_file_metadata as _gmeta

            folder_meta = _gmeta(service, file_id, resource_key=resource_key)
            if isinstance(folder_meta, dict) and 'error' in folder_meta:
                return jsonify({'error': folder_meta['error']}), 400

            folder_name = title or (folder_meta.get('name') if folder_meta else file_name)
            structure = collect_folder_structure(service, file_id)

            # Create a root CourseContentFolder mirroring the Drive folder
            root_cf = CourseContentFolder(
                course_id=course.id,
                parent_folder_id=int(folder_id) if folder_id else None,
                title=folder_name,
                order=CourseContentFolder.query.filter_by(course_id=course.id).count() + 1,
            )
            db.session.add(root_cf)
            db.session.flush()

            order_ref = [1]
            file_count = _import_drive_tree(service, structure, course.id, root_cf.id, published, allow_view, order_ref)
            db.session.commit()

            return jsonify({
                'success': True,
                'folder': True,
                'folder_name': folder_name,
                'imported_count': file_count,
            }), 200

        # Single file import
        metadata = get_file_metadata(service, file_id, resource_key=resource_key)
        if isinstance(metadata, dict) and 'error' in metadata:
            return jsonify({'error': metadata['error']}), 400

        if allow_view:
            set_file_permissions(service, file_id, make_public=True, resource_key=resource_key)

        is_image = mime_type.startswith('image/')
        view_link = create_view_only_link(service, file_id, is_image)

        content = CourseContent(
            course_id=course.id,
            title=title or metadata.get('name', file_name),
            description='',
            content_type='file',
            content_data=view_link,
            drive_file_id=file_id,
            drive_view_link=view_link,
            order=CourseContent.query.filter_by(course_id=course.id).count() + 1,
            folder_id=int(folder_id) if folder_id else None,
            is_published=published,
            allow_others_to_view=allow_view,
            is_imported=True,
        )
        db.session.add(content)
        db.session.commit()

        return jsonify({'success': True, 'content_id': content.id, 'title': content.title}), 200

    except Exception as e:
        import traceback
        current_app.logger.error(f'picker_import error: {e}\n{traceback.format_exc()}')
        db.session.rollback()
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@api_bp.route('/import-drive-file', methods=['POST'])
@limiter.limit("5 per 30 seconds")
@login_required
def import_drive_file_endpoint():
    """
    Import a file or folder from Google Drive using full drive scope.
    The file must have been selected via Google Picker for access.
    """
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400
    
    file_id = data.get('file_id')
    mime_type = data.get('mime_type', '')
    
    if not file_id:
        return jsonify({'error': 'No file ID provided'}), 400
    
    # Authenticate with Google Drive
    service = authenticate(current_user)
    if not service:
        return jsonify({
            'error': 'Google Drive not authenticated',
            'message': 'Please link your Google account first'
        }), 401
    
    try:
        # Check if it's a folder (Google Drive folder MIME type)
        if mime_type == 'application/vnd.google-apps.folder':
            result = import_drive_folder(service, file_id)
        else:
            result = import_drive_file(service, file_id)
        
        if isinstance(result, dict) and 'error' in result:
            return jsonify(result), 400
        
        return jsonify({
            'success': True,
            'message': 'File successfully imported',
            'data': result
        }), 200
        
    except Exception as e:
        import traceback
        current_app.logger.error(f'Error importing file {file_id}: {str(e)}')
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'error': 'Failed to import file',
            'message': str(e)
        }), 500

@api_bp.route('/folder/<int:folder_id>/contents', methods=['GET'])
def get_folder_contents(folder_id):
    """
    API endpoint to fetch folder contents on-demand for lazy loading.
    
    Returns published CourseContent items for the specified folder,
    with related folder data eager-loaded to prevent N+1 queries.
    
    Args:
        folder_id: The ID of the folder whose contents to retrieve
        
    Returns:
        JSON response with folder contents data
    """
    from lms.models import CourseContent, CourseContentFolder
    from sqlalchemy.orm import subqueryload
    
    try:
        # Get folder and verify it exists
        folder = CourseContentFolder.query.get(folder_id)
        if not folder:
            return jsonify({'error': 'Folder not found'}), 404
        
        # Check if user has access to this course
        course_id = folder.course_id
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Check enrollment or teacher/admin status
        course = Course.query.get(course_id)
        if not course:
            return jsonify({'error': 'Course not found'}), 404
            
        is_manager = course.is_managed_by(current_user)
        enrolled = current_user.is_authenticated and (current_user in course.users or is_manager)
        if not enrolled:
            return jsonify({'error': 'You must be enrolled in this course to view its contents'}), 403

        # Fetch published contents for this folder; students only see files the teacher made visible
        _q = CourseContent.query.filter_by(folder_id=folder_id, is_published=True)
        if not is_manager:
            _q = _q.filter_by(allow_others_to_view=True)
        contents = _q.options(
            subqueryload(CourseContent.folder)
        ).order_by(CourseContent.order).all()
        
        # Format response
        contents_data = []
        for content in contents:
            content_dict = {
                'id': content.id,
                'title': content.title,
                'description': content.description,
                'content_type': content.content_type,
                'allow_others_to_view': content.allow_others_to_view,
                'order': content.order,
                'is_published': content.is_published,
                'created_at': content.created_at.isoformat() if content.created_at else None,
                'folder_id': content.folder_id,
                'course_id': content.course_id,
                'is_downloadable': content.is_downloadable,
            }
            contents_data.append(content_dict)
        
        return jsonify({
            'success': True,
            'folder_id': folder_id,
            'course_id': course_id,
            'contents': contents_data,
            'count': len(contents_data)
        }), 200
        
    except Exception as e:
        import traceback
        current_app.logger.error(f'Error fetching folder contents for folder {folder_id}: {str(e)}')
        current_app.logger.error(traceback.format_exc())
        return jsonify({
            'error': 'Failed to fetch folder contents',
            'message': str(e)
        }), 500


def _ask_effort_cost():
    """Rate-limit cost for /ask, weighted by requested effort level (thorough costs more —
    see EFFORT_LEVELS['daily_cost'] in rag_service.py for why)."""
    from lms.rag_service import EFFORT_LEVELS, DEFAULT_EFFORT
    data = request.get_json(silent=True) or {}
    effort = data.get('effort') or DEFAULT_EFFORT
    return EFFORT_LEVELS.get(effort, EFFORT_LEVELS[DEFAULT_EFFORT])['daily_cost']


def _is_site_admin():
    """Exemption check for /ask's rate limits — site admins only (current_user.is_admin,
    full or sub-admin), deliberately not course.is_managed_by() which also covers course
    owners/teachers. Those still get rate-limited like any other user."""
    return current_user.is_authenticated and current_user.is_admin


@api_bp.route('/course/<int:course_id>/ask', methods=['POST'])
@login_required
@limiter.limit("10 per minute", exempt_when=_is_site_admin)
@limiter.limit("30 per day", cost=_ask_effort_cost, exempt_when=_is_site_admin)
def ask_course_assistant(course_id):
    """AI study assistant (Phase 6) — answers a question grounded in this course's indexed
    content only, with citations. Retrieval excludes unpublished content and anything behind
    a folder lock the asking user hasn't cleared yet (see rag_service.get_locked_content_ids)."""
    course = Course.query.get(course_id)
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    is_manager = course.is_managed_by(current_user)
    enrolled = current_user in course.users or is_manager
    if not enrolled:
        return jsonify({'error': 'You must be enrolled in this course to use its study assistant'}), 403

    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'question is required'}), 400
    if len(question) > 1000:
        return jsonify({'error': 'question is too long (max 1000 characters)'}), 400

    from lms.rag_service import answer_question, EFFORT_LEVELS, DEFAULT_EFFORT
    effort = data.get('effort') or DEFAULT_EFFORT
    if effort not in EFFORT_LEVELS:
        effort = DEFAULT_EFFORT
    result = answer_question(course, question, current_user, effort=effort)
    if result is None:
        return jsonify({'error': 'AI assistant is rate-limited right now (every available model is at capacity). Please try again in a few minutes.'}), 503

    return jsonify({'success': True, **result}), 200


@api_bp.route('/course/<int:course_id>/reindex', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def reindex_course_content(course_id):
    """Manually (re)queue RAG indexing for every content item in a course — owners/admins
    only. The recurring embedding sweep (job_manager.py) would eventually pick up anything
    new on its own; this just makes that happen immediately, and re-indexes existing items
    too (e.g. after fixing a broken upload)."""
    course = Course.query.get(course_id)
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    if not course.is_owned_by(current_user):
        return jsonify({'error': 'Only the course owner or an admin can trigger reindexing'}), 403

    from lms.job_manager import job_manager
    job_id = job_manager.queue_job('embed_course', {'course_id': course.id})
    return jsonify({'success': True, 'job_id': job_id}), 200


@api_bp.route('/course/<int:course_id>/conversation', methods=['GET'])
@login_required
def get_course_conversation(course_id):
    """Ask-AI conversation history for the current user + course, on page load. Always
    returns the user's consent status (True/False/None) so the frontend knows whether to
    show the opt-in prompt; `messages` is only populated if consent is True — a
    not-yet-answered or declined user's conversation still exists server-side (needed for
    in-session multi-turn memory) but is never displayed back on a fresh page load."""
    course = Course.query.get(course_id)
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    is_manager = course.is_managed_by(current_user)
    if not (current_user in course.users or is_manager):
        return jsonify({'error': 'You must be enrolled in this course to use its study assistant'}), 403

    from lms.rag_service import get_conversation_history
    return jsonify({'success': True, **get_conversation_history(current_user, course)}), 200


@api_bp.route('/user/ai-history-consent', methods=['POST'])
@login_required
def set_ai_history_consent():
    """Standing per-user choice of whether Ask-AI conversation history is shown back to
    them on future visits. Declining doesn't stop the conversation from being tracked
    server-side (needed for multi-turn memory within a session) — it just means it won't be
    reloaded later, and it's hard-deleted 30 days after last activity either way."""
    data = request.get_json(silent=True) or {}
    consent = data.get('consent')
    if not isinstance(consent, bool):
        return jsonify({'error': 'consent (boolean) is required'}), 400

    current_user.ai_history_consent = consent
    db.session.commit()
    return jsonify({'success': True, 'consent': consent}), 200
