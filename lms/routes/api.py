"""
API routes for courses, forum, and resources
"""
import math
import os
import re
import requests
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app, redirect, url_for, Response
from flask_login import current_user, login_required
from lms.extensions import limiter
from lms.models import Course, ForumMessage, ForumChannel, PDFDocument, Translation, db
from lms.translation_service import translation_service
from lms.google_drive_service import authenticate
from lms.upload_validation import validate_upload, UploadValidationError, PDF_MIME_TYPES, content_type_for_mime

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

def _content_media_url(content, *, download=False):
    """Resolve the URL a client should be redirected to for a CourseContent item's bytes.

    R2 wins when content.r2_key is set (see CourseContent.storage_backend); Drive's
    extension-based URL variants are the fallback for anything not yet migrated, so
    un-migrated rows keep working unchanged while the backfill runs incrementally.

    Drive needs three different serving hosts depending on file type; R2 needs exactly one
    URL for every media type, since the object's own stored Content-Type governs rendering.

    For embedding (download=False), an Office document (.doc/.docx/.ppt/.pptx/.xls/.xlsx)
    with a generated r2_preview_key is served as that converted PDF instead of the raw
    original — browsers have no native renderer for Office formats (see
    lms/office_preview.py). Downloads always get the original file, never the converted copy.
    """
    from lms import r2_client

    if not download and content.r2_preview_key:
        return r2_client.generate_presigned_url(content.r2_preview_key)

    if content.r2_key:
        disposition = None
        if download:
            # The key's basename is a fixed-width 32-hex-char uuid, a dash, then the
            # original filename (which may itself contain dashes) — see
            # r2_client.build_content_key. Slice past the uuid+dash rather than splitting on
            # '-', so a filename like "my-video-file.mp4" survives intact.
            basename = content.r2_key.rsplit('/', 1)[-1]
            original_name = basename[33:] if len(basename) > 33 and basename[32] == '-' else (content.title or 'download')
            disposition = f'attachment; filename="{original_name}"'
        return r2_client.generate_presigned_url(content.r2_key, disposition=disposition)

    if content.drive_file_id:
        file_id = content.drive_file_id
        if download:
            return f'https://drive.google.com/uc?export=download&id={file_id}'
        title_lower = (content.title or '').lower()
        if any(ext in title_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']):
            return f'https://lh3.googleusercontent.com/d/{file_id}'
        if any(ext in title_lower for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.aac']):
            return f'https://drive.google.com/uc?export=view&id={file_id}'
        return f'https://drive.google.com/file/d/{file_id}/preview'

    return None


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
                              file_mime_type=None,
                              start_seconds=None,
                              back_url=back_url,
                              current_user=current_user,
                              is_manager=is_manager,
                              course_id=course_content.course_id,
                              has_subtitles=False,
                              subtitle_language=None)


    # For other files (submissions, PDFs, etc.), redirect to the drive_view_link
    # Note: this route looks records up by drive_file_id, so R2-only CourseContent rows
    # never reach it and no template links course content here — it's now legacy-only for
    # CourseContent, still live for CourseAssignmentSubmission/PDFDocument.
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

    # 'video' is set by content-sniffing on upload/import (see upload_validation); it must
    # render in the in-app viewer like 'file' does, otherwise it falls through to a raw Drive
    # redirect that exposes the file id this route exists to hide.
    if content.content_type in ('file', 'video') and content.has_bytes:
        file_title = content.title
        back_url = url_for('main.course_page_enrolled', course_id=content.course_id)
        mime = content.file_mime_type or ''
        if mime:
            if mime.startswith('video/'):
                file_type = 'video'
            elif mime.startswith('audio/'):
                file_type = 'audio'
            elif mime.startswith('image/'):
                file_type = 'image'
            elif mime in ('application/zip', 'application/x-rar-compressed', 'application/x-rar'):
                file_type = 'unsupported'
            else:
                file_type = 'document'
        else:
            # Legacy row with no sniffed MIME on record — fall back to guessing from the title.
            file_type = 'video' if content.content_type == 'video' else 'document'
            title_lower = file_title.lower()
            if content.content_type == 'video':
                pass  # already resolved from sniffed bytes; don't let a title guess override it
            elif any(ext in title_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']):
                file_type = 'image'
            elif any(ext in title_lower for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.aac']):
                file_type = 'audio'
            elif any(ext in title_lower for ext in ['.mp4', '.webm', '.ogv', '.mov', '.avi']):
                file_type = 'video'
            elif any(ext in title_lower for ext in ['.zip', '.rar', '.7z', '.tar', '.gz']):
                file_type = 'unsupported'

        start_seconds = request.args.get('t', type=float)
        if start_seconds is not None and (start_seconds < 0 or not math.isfinite(start_seconds)):
            start_seconds = None

        from lms.subtitle_service import has_subtitles
        return render_template('file_viewer.html',
                               content_id=content_id,
                               file_title=file_title,
                               file_type=file_type,
                               file_mime_type=content.file_mime_type,
                               start_seconds=start_seconds,
                               back_url=back_url,
                               current_user=current_user,
                               is_manager=is_manager,
                               course_id=content.course_id,
                               has_subtitles=file_type in ('video', 'audio') and has_subtitles(content.id),
                               subtitle_language=content.transcript_language)

    if content.drive_view_link:
        return redirect(content.drive_view_link)
    if content.content_data and content.content_data.startswith('http'):
        return redirect(content.content_data)
    return redirect(url_for('main.index', error='file_not_found'))


@api_bp.route('/file/c/<int:content_id>/subtitles.vtt')
@login_required
def serve_content_subtitles(content_id):
    """WebVTT subtitles built on the fly from this content's stored TranscriptSegment rows
    (see subtitle_service.py) — same permission gate as the embed route, since subtitles
    reveal the same spoken content the video/audio itself already would."""
    from flask import abort
    from lms.models import CourseContent
    from lms.subtitle_service import generate_vtt

    content = CourseContent.query.get(content_id)
    if not content:
        abort(404)

    course = Course.query.get(content.course_id)
    is_manager = course.is_managed_by(current_user) if course else False
    is_enrolled = course and current_user in course.users
    if not (is_manager or is_enrolled):
        abort(403)
    if not content.is_published and not is_manager:
        abort(403)

    vtt = generate_vtt(content)
    if vtt is None:
        abort(404)
    return Response(vtt, mimetype='text/vtt')


@api_bp.route('/file/c/<int:content_id>/embed')
@login_required
def serve_content_embed(content_id):
    """Redirect to the file's actual bytes (an R2 presigned URL or a Drive embed URL)
    without exposing the storage-backend file ID in page HTML."""
    from lms.models import CourseContent, Course
    from flask import redirect, abort

    content = CourseContent.query.get(content_id)
    if not content or not content.has_bytes:
        abort(404)

    course = Course.query.get(content.course_id)
    is_manager = course.is_managed_by(current_user) if course else False
    is_enrolled = course and current_user in course.users
    if not (is_manager or is_enrolled):
        abort(403)
    if not content.is_published and not is_manager:
        abort(403)

    url = _content_media_url(content)
    if not url:
        abort(404)
    resp = redirect(url)
    # A presigned URL is only valid for a limited window — without no-store, a browser/bfcache
    # could replay one after it expires (e.g. a tab left open past R2_URL_EXPIRY_SECONDS),
    # producing a confusing mid-video 403 instead of a fresh redirect on the next load.
    resp.headers['Cache-Control'] = 'private, no-store'
    return resp


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

    if content.has_bytes:
        url = _content_media_url(content, download=True)
        if url:
            return redirect(url)

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


_GOOGLE_NATIVE_MIME_PREFIX = 'application/vnd.google-apps.'


def _copy_drive_file_to_r2(service, file_id, course_id, name, mime, resource_key=None, size_hint=None):
    """Download a Picker-selected Drive file's bytes and copy them into R2.

    Returns (r2_key, effective_mime, r2_preview_key) on success, or (None, reason, None) on
    failure/skip — `reason` is a short, user-facing string explaining why (e.g. 'google_doc',
    'too_large', 'download_failed'). Google-native Docs/Sheets/Slides have no raw file bytes to
    copy and are skipped rather than exported, per the deliberate scope decision for this
    feature. `r2_preview_key` is set only for Office documents needing a converted PDF preview
    to be viewable at all (see lms/office_preview.py) — None for everything else.

    Runs inside a background job (lms.job_manager._execute_picker_import_file_job /
    _execute_picker_import_folder_job — see picker_import in this file for the enqueue side),
    not inline in a request — `size_hint` (Drive's own declared file size, when the caller has
    it) still lets an oversized file be rejected before spending time downloading it at all.
    """
    import tempfile
    import filetype as _filetype
    from lms import office_preview, r2_client
    from lms.routes import UPLOAD_STAGING_DIR
    from lms.google_drive_service import download_file as _drive_download

    if mime and mime.startswith(_GOOGLE_NATIVE_MIME_PREFIX):
        return None, 'google_doc', None

    max_bytes = current_app.config.get('MAX_CONTENT_LENGTH')
    if max_bytes and size_hint:
        try:
            if int(size_hint) > max_bytes:
                return None, 'too_large', None
        except (TypeError, ValueError):
            pass

    os.makedirs(UPLOAD_STAGING_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=UPLOAD_STAGING_DIR)
    os.close(fd)
    try:
        if not _drive_download(service, file_id, tmp_path, resource_key=resource_key):
            return None, 'download_failed', None

        if max_bytes and os.path.getsize(tmp_path) > max_bytes:
            return None, 'too_large', None

        effective_mime = mime
        if not effective_mime or effective_mime == 'application/octet-stream':
            kind = _filetype.guess(tmp_path)
            effective_mime = kind.mime if kind else effective_mime

        key = r2_client.build_content_key(course_id, name)
        if not r2_client.upload_file(tmp_path, key, content_type=effective_mime, filename=name):
            return None, 'upload_failed', None

        preview_key = office_preview.generate_and_upload_preview(tmp_path, effective_mime, key)
        return key, effective_mime, preview_key
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _import_drive_tree(service, structure, course_id, parent_folder_id, published, allow_view, order_ref):
    """Recursively mirror a Drive folder tree into CourseContentFolder / CourseContent rows,
    copying each file's bytes into R2 along the way (see _copy_drive_file_to_r2).

    order_ref is a one-element list [int] used as a mutable counter shared across calls.
    Returns (created, skipped) counts.
    """
    from lms.models import CourseContent, CourseContentFolder
    from lms.google_drive_service import get_file_metadata as _gmeta

    created = 0
    skipped = 0

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
        sub_created, sub_skipped = _import_drive_tree(service, folder_info['structure'], course_id, cf.id, published, allow_view, order_ref)
        created += sub_created
        skipped += sub_skipped

    for file_info in structure.get('files', []):
        metadata = _gmeta(service, file_info['id'])
        if isinstance(metadata, dict) and 'error' in metadata:
            skipped += 1
            continue
        mime = metadata.get('mimeType') or file_info.get('mime_type')
        name = metadata.get('name') or file_info['name']
        size_hint = metadata.get('size') or file_info.get('size')
        key, effective_mime_or_reason, preview_key = _copy_drive_file_to_r2(service, file_info['id'], course_id, name, mime, size_hint=size_hint)
        if not key:
            current_app.logger.info(f"Skipped Picker import of '{name}': {effective_mime_or_reason}")
            skipped += 1
            continue
        item = CourseContent(
            course_id=course_id,
            title=name,
            description='',
            # The copied bytes' own MIME decides this — a lecture must land as 'video' or the
            # RAG pipeline never transcribes it (see rag_service.extract_text_for_content).
            content_type=content_type_for_mime(effective_mime_or_reason),
            content_data='',
            r2_key=key,
            r2_preview_key=preview_key,
            file_mime_type=effective_mime_or_reason,
            drive_file_id=file_info['id'],  # provenance only — serving/RAG prefer r2_key
            drive_view_link=None,
            order=order_ref[0],
            folder_id=parent_folder_id,
            is_published=published,
            allow_others_to_view=allow_view,
            is_imported=True,
        )
        db.session.add(item)
        order_ref[0] += 1
        created += 1

    return created, skipped


@api_bp.route('/picker-import', methods=['POST'])
@limiter.limit("10 per minute")
@login_required
def picker_import():
    """
    Queue import of a file or folder the teacher selected via the Google Picker as a
    background job — the actual work (Drive download, optional LibreOffice conversion, R2
    upload, and for a folder, recursively doing that per file) can run for a long time,
    previously inline in this request against gunicorn's 600s timeout. See
    lms.job_manager._execute_picker_import_file_job / _execute_picker_import_folder_job for
    the work itself, and picker_import_status below for the poll side.
    """
    from lms.models import Course

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

    # Checked synchronously (cheap — a token refresh, no Drive/R2 traffic) so a missing link
    # fails fast instead of after a job round-trip. The job itself re-authenticates as this
    # user rather than reusing this connection — a googleapiclient service object can't be
    # put in job.data (not JSON-serializable) or carried across the process boundary to the
    # worker.
    if not authenticate(current_user):
        return jsonify({'error': 'no_token', 'message': 'Please link your Google account first'}), 401

    job_data = {
        'user_id': current_user.id,
        'course_id': course.id,
        'file_id': file_id,
        'file_name': file_name,
        'mime_type': mime_type,
        'resource_key': resource_key,
        'folder_id': folder_id,
        'title': title,
        'published': published,
        'allow_view': allow_view,
    }

    from lms.job_manager import job_manager
    job_type = 'picker_import_folder' if mime_type == 'application/vnd.google-apps.folder' else 'picker_import_file'
    job_id = job_manager.queue_job(job_type, job_data)

    return jsonify({'success': True, 'job_id': job_id}), 202


@api_bp.route('/picker-import/status/<job_id>', methods=['GET'])
@login_required
def picker_import_status(job_id):
    """Poll side of the background Picker-import job queued by picker_import."""
    from lms.job_manager import job_manager, JobStatus
    job = job_manager.get_job(job_id)
    job_data = job.data if job else None
    if not job or job.type not in ('picker_import_file', 'picker_import_folder') \
            or not job_data or job_data.get('user_id') != current_user.id:
        return jsonify({'error': 'Job not found'}), 404

    if job.status == JobStatus.COMPLETED:
        return jsonify({'success': True, 'status': 'completed', **(job.result or {})}), 200
    if job.status == JobStatus.FAILED:
        return jsonify({'success': False, 'status': 'failed', 'error': job.error or 'Import failed.'}), 200
    return jsonify({'success': True, 'status': job.status}), 200


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


def _moment_flag_rate_key():
    """Per-user, not per-IP: a whole cohort watching the same lecture from one campus
    network is the intended signal for video-moment flagging, not abuse — get_remote_address
    (the shared limiter's default) would throttle the very convergence the weighting relies
    on. Falls back to IP only for the (route-blocked, but defensive) unauthenticated case."""
    if current_user.is_authenticated:
        return f'user:{current_user.id}'
    from flask_limiter.util import get_remote_address
    return get_remote_address()


@api_bp.route('/content/<int:content_id>/moment-flag', methods=['POST'])
@login_required
@limiter.limit("6 per minute", key_func=_moment_flag_rate_key)
@limiter.limit("60 per day", key_func=_moment_flag_rate_key, exempt_when=_is_site_admin)
def flag_video_moment(content_id):
    """Student (or teacher) marks the video's current playback position as worth
    highlighting (video moment highlighting, Phase 6 addendum). A teacher's own flag
    instantly queues that moment for captioning, bypassing the weight threshold — see the
    fast-path below; a student's flag just contributes one vote, counted at most once per
    account per ~45s bucket (enforced by a DB unique constraint, not application logic)."""
    from sqlalchemy.exc import IntegrityError
    from lms.models import ContentEmbedding, CourseContent, Enrollment, VideoMoment, VideoMomentFlag
    from lms.moment_service import bucket_for
    from lms.rag_service import SEGMENT_CHUNK_WINDOW_SECONDS

    content = CourseContent.query.get(content_id)
    if not content:
        return jsonify({'error': 'Content not found'}), 404

    course = Course.query.get(content.course_id)
    is_manager = course.is_managed_by(current_user) if course else False
    is_enrolled = course and current_user in course.users
    if not (is_manager or is_enrolled):
        return jsonify({'error': 'forbidden'}), 403
    if not content.is_published and not is_manager:
        return jsonify({'error': 'forbidden'}), 403

    if content.content_type != 'video' or not content.has_bytes:
        return jsonify({'error': 'This content cannot be flagged.'}), 400

    data = request.get_json(silent=True) or {}
    timestamp_seconds = data.get('timestamp_seconds')
    try:
        timestamp_seconds = float(timestamp_seconds)
    except (TypeError, ValueError):
        return jsonify({'error': 'timestamp_seconds is required'}), 400
    if not math.isfinite(timestamp_seconds) or timestamp_seconds < 0:
        return jsonify({'error': 'Invalid timestamp'}), 400

    # Bound against the transcript's own known extent when available (exact); otherwise a
    # generous sanity ceiling — an untranscribed video has no moments worth promoting yet
    # regardless, so a loose bound here costs nothing.
    known_end = (
        db.session.query(db.func.max(ContentEmbedding.end_seconds))
        .filter_by(course_content_id=content.id).scalar()
    )
    max_allowed = (known_end + SEGMENT_CHUNK_WINDOW_SECONDS) if known_end else 24 * 3600
    if timestamp_seconds > max_allowed:
        return jsonify({'error': 'Invalid timestamp'}), 400

    if not is_manager:
        enrollment = Enrollment.query.filter_by(user_id=current_user.id, course_id=course.id).first()
        if enrollment and enrollment.moment_flags_blocked:
            return jsonify({'error': 'forbidden'}), 403

    bucket = bucket_for(timestamp_seconds)

    blocked_moment = VideoMoment.query.filter_by(
        course_content_id=content.id, bucket_index=bucket, status='blocked',
    ).first()
    if blocked_moment:
        # Don't tell the student they've been singled out — just no-op as if it worked.
        return jsonify({'success': True, 'already_flagged': True})

    db.session.add(VideoMomentFlag(
        course_content_id=content.id,
        timestamp_seconds=timestamp_seconds,
        bucket_index=bucket,
        source='student',
        added_by=current_user.id,
    ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': True, 'already_flagged': True})

    if is_manager:
        # Teacher flag = instant promotion: queue this bucket for captioning regardless of
        # weight. Idempotent — no-ops if the bucket's already pending/captioned/blocked. The
        # sweep's existing retry branch picks this row up like any other pending moment, so
        # no special-casing is needed there.
        exists = VideoMoment.query.filter_by(course_content_id=content.id, bucket_index=bucket).first()
        if not exists:
            db.session.add(VideoMoment(
                course_content_id=content.id,
                bucket_index=bucket,
                timestamp_seconds=timestamp_seconds,
                weight_at_promotion=0,
                status='pending',
            ))
            db.session.commit()

    return jsonify({'success': True, 'already_flagged': False})


@api_bp.route('/content/<int:content_id>/moments', methods=['GET'])
@login_required
def list_video_moments(content_id):
    """Manager-only: the live weighted-candidate view plus already-decided VideoMoment rows,
    for the moments panel in file_viewer.html."""
    from lms.models import CourseContent, Enrollment, User, VideoMoment, VideoMomentFlag
    from lms.moment_service import candidate_buckets
    from lms.rag_service import _format_timestamp

    content = CourseContent.query.get(content_id)
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    course = Course.query.get(content.course_id)
    if not course or not course.is_managed_by(current_user):
        return jsonify({'error': 'forbidden'}), 403

    candidates = {
        (c['course_content_id'], c['bucket_index']): c
        for c in candidate_buckets() if c['course_content_id'] == content_id
    }
    decided = VideoMoment.query.filter_by(course_content_id=content_id).all()

    blocked_user_ids = {
        e.user_id for e in Enrollment.query.filter_by(course_id=course.id, moment_flags_blocked=True).all()
    }

    # Who flagged each bucket — lets the panel offer a per-student "block"/"unblock" action
    # inline, not just a bucket-level one.
    flaggers_by_bucket: dict[int, list[dict]] = {}
    student_flags = (
        db.session.query(VideoMomentFlag, User)
        .join(User, VideoMomentFlag.added_by == User.id)
        .filter(VideoMomentFlag.course_content_id == content_id, VideoMomentFlag.source == 'student')
        .all()
    )
    for flag, user in student_flags:
        flaggers_by_bucket.setdefault(flag.bucket_index, []).append({
            'user_id': user.id, 'username': user.username, 'blocked': user.id in blocked_user_ids,
        })

    rows = []
    seen_buckets = set()
    for m in decided:
        seen_buckets.add(m.bucket_index)
        rows.append({
            'bucket_index': m.bucket_index,
            'timestamp_seconds': m.timestamp_seconds,
            'formatted_timestamp': _format_timestamp(m.timestamp_seconds),
            'weight': m.weight_at_promotion,
            'status': m.status,
            'caption': m.caption,
            'flaggers': flaggers_by_bucket.get(m.bucket_index, []),
        })
    for (cid, bucket), c in candidates.items():
        if bucket in seen_buckets:
            continue
        rows.append({
            'bucket_index': bucket,
            'timestamp_seconds': c['timestamp_seconds'],
            'formatted_timestamp': _format_timestamp(c['timestamp_seconds']),
            'weight': c['weight'],
            'status': 'candidate',
            'caption': None,
            'flaggers': flaggers_by_bucket.get(bucket, []),
        })

    rows.sort(key=lambda r: r['timestamp_seconds'])
    return jsonify({'success': True, 'moments': rows})


@api_bp.route('/content/<int:content_id>/moments/block', methods=['POST'])
@login_required
def block_video_moment(content_id):
    """Manager-only: block (or unblock) a specific timestamp bucket. Blocking stops it from
    ever being (re-)promoted, and if it was already captioned, removes it from Ask AI
    immediately. Unblocking a never-captioned bucket just deletes the placeholder row,
    returning it to a normal re-evaluated candidate; unblocking a previously-captioned one
    restores its citation from the still-stored caption text — no new vision API call."""
    from lms.models import ContentEmbedding, CourseContent, VideoMoment
    from lms.moment_service import _store_caption_embedding
    from lms.rag_service import SEGMENT_CHUNK_WINDOW_SECONDS

    content = CourseContent.query.get(content_id)
    if not content:
        return jsonify({'error': 'Content not found'}), 404
    course = Course.query.get(content.course_id)
    if not course or not course.is_managed_by(current_user):
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    try:
        bucket_index = int(data.get('bucket_index'))
    except (TypeError, ValueError):
        return jsonify({'error': 'bucket_index is required'}), 400
    blocked = bool(data.get('blocked', True))

    moment = VideoMoment.query.filter_by(course_content_id=content_id, bucket_index=bucket_index).first()

    if blocked:
        if moment:
            if moment.status == 'captioned':
                ContentEmbedding.query.filter(
                    ContentEmbedding.course_content_id == content_id,
                    ContentEmbedding.start_seconds == moment.timestamp_seconds,
                ).delete()
            moment.status = 'blocked'
        else:
            db.session.add(VideoMoment(
                course_content_id=content_id, bucket_index=bucket_index,
                timestamp_seconds=bucket_index * SEGMENT_CHUNK_WINDOW_SECONDS,
                status='blocked', weight_at_promotion=0,
            ))
    else:
        if not moment or moment.status != 'blocked':
            return jsonify({'error': 'This moment is not currently blocked.'}), 400
        if moment.caption:
            moment.status = 'captioned'
            _store_caption_embedding(content, moment)
        else:
            db.session.delete(moment)

    db.session.commit()
    return jsonify({'success': True, 'blocked': blocked})


@api_bp.route('/course/<int:course_id>/moment-flags/block-user', methods=['POST'])
@login_required
def block_moment_flagger(course_id):
    """Manager-only: block/unblock a student from flagging video moments in this course.
    Effective immediately in both directions — weight is computed live (moment_service.
    candidate_buckets), so a block instantly removes that student's influence from every
    bucket they've ever touched, with no backfill needed."""
    from lms.models import Enrollment

    course = Course.query.get(course_id)
    if not course or not course.is_managed_by(current_user):
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    try:
        user_id = int(data.get('user_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'user_id is required'}), 400
    blocked = bool(data.get('blocked', True))

    enrollment = Enrollment.query.filter_by(user_id=user_id, course_id=course_id).first()
    if not enrollment:
        return jsonify({'error': 'That user is not enrolled in this course.'}), 404

    enrollment.moment_flags_blocked = blocked
    db.session.commit()
    return jsonify({'success': True, 'blocked': blocked})


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

    from lms.rag_service import EFFORT_LEVELS, DEFAULT_EFFORT
    effort = data.get('effort') or DEFAULT_EFFORT
    if effort not in EFFORT_LEVELS:
        effort = DEFAULT_EFFORT

    # Runs as a background job, not inline — answer_question's Gemini call chain takes
    # several real seconds (more under 'thorough'), and gunicorn's sync workers here are few
    # (see deploy/gunicorn_config.py); holding one that long blocks every other request on the
    # site. The frontend polls ask_course_assistant_status below for the result.
    from lms.job_manager import job_manager
    job_id = job_manager.queue_job('answer_question', {
        'course_id': course.id,
        'user_id': current_user.id,
        'question': question,
        'effort': effort,
    })
    return jsonify({'success': True, 'job_id': job_id}), 202


@api_bp.route('/course/<int:course_id>/ask/status/<job_id>', methods=['GET'])
@login_required
@limiter.limit("120 per minute")
def ask_course_assistant_status(course_id, job_id):
    """Poll side of the background Ask AI job queued by ask_course_assistant. Scoped to the
    requesting user and course — job ids are UUIDs (hard to guess), but an AI answer can
    quote private course content, so this still checks ownership rather than trusting the id
    alone."""
    from lms.job_manager import job_manager, JobStatus
    job = job_manager.get_job(job_id)
    job_data = job.data if job else None
    if not job or job.type != 'answer_question' or not job_data \
            or job_data.get('course_id') != course_id or job_data.get('user_id') != current_user.id:
        return jsonify({'error': 'Job not found'}), 404

    if job.status == JobStatus.COMPLETED:
        return jsonify({'success': True, 'status': 'completed', **(job.result or {})}), 200
    if job.status == JobStatus.FAILED:
        return jsonify({'success': False, 'status': 'failed', 'error': job.error or 'Something went wrong.'}), 200
    return jsonify({'success': True, 'status': job.status}), 200


@api_bp.route('/course/<int:course_id>/reindex', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def reindex_course_content(course_id):
    """Manually (re)queue RAG indexing for every content item in a course — site admins
    only. The recurring embedding sweep (job_manager.py) would eventually pick up anything
    new on its own; this just makes that happen immediately, and re-indexes existing items
    too (e.g. after fixing a broken upload)."""
    course = Course.query.get(course_id)
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    if not current_user.is_admin:
        return jsonify({'error': 'Only a site admin can trigger reindexing'}), 403

    from lms.job_manager import job_manager
    job_id = job_manager.queue_job('embed_course', {'course_id': course.id})
    return jsonify({'success': True, 'job_id': job_id}), 200


@api_bp.route('/course/<int:course_id>/promote-moments', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def promote_course_moments(course_id):
    """Manually trigger the video-moment promotion sweep for this course right now, instead
    of waiting up to MOMENT_PROMOTION_INTERVAL_MINUTES — site admins only, same restriction
    as reindexing (this also spends real Gemini vision API calls, so it's not opened up to
    course owners/teachers the way reindexing briefly was)."""
    course = Course.query.get(course_id)
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    if not current_user.is_admin:
        return jsonify({'error': 'Only a site admin can trigger this'}), 403

    from lms.job_manager import job_manager
    job_id = job_manager.queue_job('promote_moments', {'course_id': course.id})
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
