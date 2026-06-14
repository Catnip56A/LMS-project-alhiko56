"""
API routes for courses, forum, and resources
"""
import os
import time
import re
import logging
import requests
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app, redirect, url_for, Response
from flask_login import current_user, login_required
from flask_babel import _
from yonca.extensions import limiter
from yonca.models import Course, ForumMessage, ForumChannel, Resource, PDFDocument, Translation, db
from yonca.translation_service import translation_service
from yonca.google_drive_service import authenticate, upload_file, create_view_only_link, set_file_permissions, import_drive_file, import_drive_folder

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
    from yonca.content_translator import get_translated_content, get_translated_string_array
    from yonca.models import PageLimitation
    
    # Get language from query parameter, or fall back to session language
    user_locale = request.args.get('lang', session.get('language', 'en'))

    # Enforce admin-set page limitations for API access
    limitation = PageLimitation.query.filter_by(page_key='courses').first()
    if limitation and limitation.is_limited:
        if not (current_user.is_authenticated and current_user.is_admin):
            return jsonify({'error': 'Page blocked by admin'}), 403
    
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
            'dropdown_menu': c.dropdown_menu,
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
            'dropdown_menu': c.dropdown_menu,
            'tags': get_translated_string_array('course', c.id, 'tags', c.tags, user_locale)
        } for c in courses])

@api_bp.route('/user')
def get_current_user():
    """Get current user information"""
    from flask import session
    from yonca.content_translator import get_translated_content, get_translated_string_array
    
    # Get user's current locale
    user_locale = session.get('language', 'en')
    
    if current_user.is_authenticated:
        return jsonify({
            'id': current_user.id,
            'username': current_user.username,
            'is_admin': current_user.is_admin,
            'courses': [{
                'id': c.id,
                'title': get_translated_content('course', c.id, 'title', c.title, user_locale),
                'description': get_translated_content('course', c.id, 'description', c.description, user_locale),
                'time_slot': c.time_slot,
                'dropdown_menu': c.dropdown_menu,
                'tags': get_translated_string_array('course', c.id, 'tags', c.tags, user_locale)
            } for c in current_user.courses]
        })
    else:
        return jsonify(None)


@api_bp.route('/page_limitation/<page_key>')
def get_page_limitation(page_key):
    """Return whether a page is limited and an admin message (if limited).

    This endpoint is used by the SPA to decide whether to show a static page
    (like the MOXO page) or to redirect the user when admins have blocked it.
    """
    from yonca.models import PageLimitation
    from flask_babel import gettext

    # Normalize input to prevent injection via URL
    page_key = page_key.strip()[:50]

    limitation = PageLimitation.query.filter_by(page_key=page_key).first()
    is_limited = bool(limitation and limitation.is_limited)

    # Admins always allowed
    if is_limited and (not (current_user.is_authenticated and current_user.is_admin)):
        message = gettext('ADMIN BLOCKED THE PAGE, to get further information, contact the admins of the website')
    else:
        message = ''

    return jsonify({'page_key': page_key, 'is_limited': is_limited, 'message': message})

@api_bp.route('/forum/channels')
def get_forum_channels():
    """Get all active forum channels"""
    from yonca.models import PageLimitation

    # Enforce forum limitation
    limitation = PageLimitation.query.filter_by(page_key='forum').first()
    if limitation and limitation.is_limited:
        if not (current_user.is_authenticated and current_user.is_admin):
            return jsonify({'error': 'Page blocked by admin'}), 403
    channels = ForumChannel.query.filter_by(is_active=True).order_by(ForumChannel.sort_order).all()
    
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'description': c.description,
        'requires_login': c.requires_login,
        'admin_only': c.admin_only
    } for c in channels])

@api_bp.route('/forum/messages')
def get_forum_messages():
    """Get forum messages, optionally filtered by channel"""
    channel_slug = request.args.get('channel', 'general')
    from yonca.models import PageLimitation

    # Enforce forum limitation for message listing
    limitation = PageLimitation.query.filter_by(page_key='forum').first()
    if limitation and limitation.is_limited:
        if not (current_user.is_authenticated and current_user.is_admin):
            return jsonify({'error': 'Page blocked by admin'}), 403
    
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
    from yonca.models import PageLimitation

    # Enforce forum limitation for posting
    limitation = PageLimitation.query.filter_by(page_key='forum').first()
    if limitation and limitation.is_limited:
        if not (current_user.is_authenticated and current_user.is_admin):
            return jsonify({'error': 'Page blocked by admin'}), 403
    
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

@api_bp.route('/resources', methods=['POST'])
@login_required
def upload_resource():
    """Upload a new learning resource"""
    from flask import request
    from werkzeug.utils import secure_filename
    import os
    import random
    import string
    from flask_login import current_user
    
    # Check if user is authenticated and is admin
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    # Check if user has Google OAuth tokens
    if not current_user.google_access_token:
        return jsonify({
            'error': 'Google Drive access required. Please connect your Google account in the admin panel first.',
            'login_required': True,
            'login_url': url_for('google_login.index', _external=True)
        }), 403
    
    # Check if file is present
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Get form data
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    tags = request.form.get('tags', '').strip()
    pin_enabled = 'pin_enabled' in request.form  # Checkbox is checked if present in form data
    
    if not title:
        return jsonify({'error': 'Title is required'}), 400
    
    # Create temporary directory if it doesn't exist
    temp_dir = os.path.join(current_app.static_folder, 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Authenticate with Google Drive
    service = authenticate()
    if not service:
        return jsonify({'error': 'Failed to authenticate with Google Drive'}), 500
    
    # Handle preview image upload
    preview_image_url = None
    if 'preview_image' in request.files:
        preview_file = request.files['preview_image']
        if preview_file and preview_file.filename != '':
            # Generate secure filename for preview image
            preview_filename = secure_filename(preview_file.filename)
            preview_unique_filename = f"preview_{random.randint(1000, 9999)}_{preview_filename}"
            preview_temp_path = os.path.join(temp_dir, preview_unique_filename)
            
            # Save preview image temporarily
            preview_file.save(preview_temp_path)
            
            # Upload preview image to Google Drive
            try:
                preview_drive_file_id = upload_file(service, preview_temp_path, preview_filename)
                if preview_drive_file_id:
                    # Set permissions for preview image
                    try:
                        set_file_permissions(service, preview_drive_file_id, make_public=True)
                    except Exception as e:
                        print(f"Error setting preview permissions: {e}")
                    # Create view-only link for preview image
                    preview_image_url = create_view_only_link(service, preview_drive_file_id, is_image=True)
                    preview_drive_view_link = preview_image_url  # Store the view link
            except Exception as e:
                print(f"Error uploading preview to Drive: {e}")
                if "insufficientPermissions" in str(e) or "403" in str(e):
                    return jsonify({'error': 'Your Google account does not have sufficient permissions. Please re-link your Google account with full Drive access.'}), 403
            
            # Clean up temporary preview file
            try:
                os.remove(preview_temp_path)
            except:
                pass
    
    # PIN is now always auto-generated (no user input allowed)
    
    try:
        
        # Generate secure filename
        filename = secure_filename(file.filename)
        unique_filename = f"{random.randint(1000, 9999)}_{filename}"
        temp_file_path = os.path.join(temp_dir, unique_filename)
        
        # Save file temporarily
        file.save(temp_file_path)
        
        # Upload to Google Drive
        try:
            drive_file_id = upload_file(service, temp_file_path, filename)
        except Exception as e:
            print(f"Error uploading to Drive: {e}")
            if "insufficientPermissions" in str(e) or "403" in str(e):
                return jsonify({'error': 'Your Google account does not have sufficient permissions. Please re-link your Google account with full Drive access.'}), 403
            return jsonify({'error': 'Failed to upload file to Google Drive'}), 500
        
        if not drive_file_id:
            return jsonify({'error': 'Failed to upload file to Google Drive'}), 500
        
        # Set file permissions to make it publicly accessible
        try:
            success = set_file_permissions(service, drive_file_id, make_public=True)
            print(f"DEBUG: set_file_permissions for resource {drive_file_id} returned: {success}")
        except Exception as e:
            print(f"Error setting file permissions: {e}")
            # Continue anyway - view link creation might still work
        
        # Create view-only link - check if file is an image
        is_image = is_image_file(file.filename)
        print(f"DEBUG: File {file.filename} detected as image: {is_image}")
        view_link = create_view_only_link(service, drive_file_id, is_image=is_image)
        if not view_link:
            return jsonify({'error': 'Failed to create view link'}), 500
        
        # Create database record
        new_resource = Resource(
            title=title,
            description=description,
            tags=tags,
            preview_image=preview_image_url,
            preview_drive_file_id=preview_drive_file_id if 'preview_drive_file_id' in locals() and preview_drive_file_id else None,
            preview_drive_view_link=preview_drive_view_link if 'preview_drive_view_link' in locals() and preview_drive_view_link else None,
            drive_file_id=drive_file_id,
            drive_view_link=view_link,
            is_image_file=is_image,
            uploaded_by=current_user.id
        )
        
        # Conditionally set PIN based on user choice
        if not pin_enabled:
            new_resource.access_pin = None
            new_resource.pin_expires_at = None
        
        db.session.add(new_resource)
        db.session.commit()
        
        # Clean up temporary file
        try:
            os.remove(temp_file_path)
        except:
            pass
        
        return jsonify({
            'success': True,
            'id': new_resource.id,
            'title': new_resource.title,
            'drive_view_link': new_resource.drive_view_link,
            'pin': new_resource.access_pin,
            'expires_at': new_resource.pin_expires_at.isoformat() if new_resource.pin_expires_at else None,
            'pin_enabled': pin_enabled,
            'message': 'Resource uploaded successfully'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        # Clean up temporary file if it was saved
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@api_bp.route('/resources')
def get_resources():
    """Get all learning resources"""
    from flask_login import current_user
    from datetime import datetime
    from flask import session
    from yonca.content_translator import get_translated_content
    from yonca.models import PageLimitation

    # Enforce resources limitation for API access
    limitation = PageLimitation.query.filter_by(page_key='resources').first()
    if limitation and limitation.is_limited:
        if not (current_user.is_authenticated and current_user.is_admin):
            return jsonify({'error': 'Page blocked by admin'}), 403

    # Get user's current locale from session
    user_locale = session.get('language', 'en')

    resources = Resource.query.filter_by(is_active=True).all()
    result = []

    for r in resources:
        # Check if PIN has expired and regenerate if needed
        if r.is_pin_expired():
            r.reset_pin()
            db.session.commit()

        # Get translated title and description
        translated_title = get_translated_content('resource', r.id, 'title', r.title, user_locale)
        translated_description = get_translated_content('resource', r.id, 'description', r.description, user_locale)

        resource_data = {
            'id': r.id,
            'title': translated_title,
            'description': translated_description,
            'tags': ' '.join([_(tag.strip()) for tag in (r.tags or '').split() if tag.strip()]),
            'preview_image': r.preview_image,
            'preview_drive_file_id': r.preview_drive_file_id,
            'preview_drive_view_link': r.preview_drive_view_link,
            'drive_view_link': r.drive_view_link,
            'upload_date': r.upload_date.isoformat() if r.upload_date else None,
            'pin_expires_at': r.pin_expires_at.isoformat() if r.pin_expires_at else None,
            'pin_last_reset': r.pin_last_reset.isoformat() if r.pin_last_reset else None,
            'has_pin': bool(r.access_pin),
            'uploaded_by': r.uploaded_by
        }

        # Check if user has permanent access to this resource
        has_permanent_access = current_user.is_authenticated and r in current_user.accessed_resources
        
        if has_permanent_access:
            # User has already accessed this resource, show view link directly
            resource_data['permanent_access'] = True
            resource_data['access_granted'] = True
        elif not current_user.is_authenticated:
            # Non-authenticated users need to log in
            resource_data['permanent_access'] = False
            resource_data['requires_login'] = True
        else:
            # Authenticated users who don't have permanent access need PIN
            resource_data['permanent_access'] = False
            resource_data['requires_pin'] = True
            if current_user.is_admin or r.uploaded_by == current_user.id:
                resource_data['access_pin'] = r.access_pin

        result.append(resource_data)

    return jsonify(result)

@api_bp.route('/resources/<int:resource_id>/reset-pin', methods=['POST'])
@login_required
def reset_resource_pin(resource_id):
    """Reset the PIN for a specific resource (admin only)"""
    # Check if user is admin
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403

    resource = Resource.query.get_or_404(resource_id)

    # Reset the PIN
    old_pin = resource.access_pin
    resource.reset_pin()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'PIN reset successfully',
        'new_pin': resource.access_pin,
        'expires_at': resource.pin_expires_at.isoformat(),
        'old_pin': old_pin
    }), 200

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

@api_bp.route('/resources/<int:resource_id>/access', methods=['POST'])
@login_required
def access_resource(resource_id):
    """Verify PIN and provide access to resource, recording user access for permanent viewing"""
    data = request.get_json()
    
    if not data or 'pin' not in data:
        return jsonify({'error': 'PIN required'}), 400
    
    resource = Resource.query.filter_by(id=resource_id, is_active=True).first()
    if not resource:
        return jsonify({'error': 'Resource not found'}), 404
    
    if not resource.access_pin or resource.access_pin != data['pin']:
        return jsonify({'error': 'Invalid PIN'}), 403
    
    # Record that this user has accessed this resource
    from flask_login import current_user
    if resource not in current_user.accessed_resources:
        current_user.accessed_resources.append(resource)
        db.session.commit()
    
    return jsonify({
        'success': True,
        'title': resource.title,
        'drive_view_link': resource.drive_view_link,
        'permanent_access': True
    })

@api_bp.route('/resources/<int:resource_id>/download/<pin>')
@login_required
def download_resource(resource_id, pin):
    """Get resource view link with PIN verification and expiration check"""
    resource = Resource.query.filter_by(id=resource_id, is_active=True).first()
    if not resource:
        return jsonify({'error': 'Resource not found'}), 404

    # Check PIN
    if resource.access_pin != pin:
        return jsonify({'error': 'Invalid PIN'}), 403

    # Check if PIN has expired
    if resource.is_pin_expired():
        return jsonify({'error': 'PIN has expired. Please request a new PIN from the resource owner.'}), 403

    # Return the view link
    return jsonify({
        'success': True,
        'title': resource.title,
        'drive_view_link': resource.drive_view_link
    })

@api_bp.route('/pdfs/upload', methods=['POST'])
@limiter.limit("5 per 30 seconds")
def upload_pdf():
    """Upload a new PDF document"""
    from flask import request
    from werkzeug.utils import secure_filename
    import os
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
        from yonca.google_drive_service import authenticate, upload_file, create_view_only_link
        service = authenticate()
        if not service:
            return jsonify({'error': 'Failed to authenticate with Google Drive'}), 500
        
        try:
            drive_file_id = upload_file(service, temp_file_path, filename)
        except Exception as e:
            print(f"Error uploading to Drive: {e}")
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
        except:
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
            except:
                pass
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@api_bp.route('/user')
def get_user():
    """Get current user information (or null if not authenticated)"""
    if current_user.is_authenticated:
        return jsonify({
            'id': current_user.id,
            'username': current_user.username,
            'email': current_user.email,
            'is_admin': current_user.is_admin,
            'preferred_language': current_user.preferred_language,
            'courses': [{'id': c.id, 'title': c.title, 'description': c.description} for c in current_user.courses]
        })
    else:
        return jsonify(None)

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
    content_type = data.get('content_type', 'home_content')
    content_id = data.get('content_id')
    field_name = data.get('field_name')

    if not text or not content_id or not field_name:
        return jsonify({'error': 'text, content_id and field_name are required'}), 400

    try:
        from yonca.content_translator import translate_content
        from yonca.models import db
        saved = translate_content(content_type, int(content_id), field_name, text)
        if not saved:
            return jsonify({'error': 'Translation service unavailable. Start LibreTranslate with: just libre'}), 503
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
    from yonca.models import ContentView, db

    # sendBeacon with URLSearchParams sends form-urlencoded; JSON browser sends application/json
    data = request.get_json(silent=True) or request.form

    content_type = data.get('content_type')
    content_id   = data.get('content_id')
    viewing_duration = data.get('viewing_duration', 0)

    if not content_type or not content_id:
        return jsonify({'error': 'Content type and content ID are required'}), 400

    try:
        # Create a new content view record
        content_view = ContentView(
            user_id=current_user.id,
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

@api_bp.route('/feature-images/upload', methods=['POST'])
@limiter.limit("5 per 30 seconds")
@login_required
def upload_feature_image():
    """Upload feature image to Google Drive"""
    # Check if user has Google OAuth tokens
    if not current_user.google_access_token:
        return jsonify({
            'error': 'Google Drive access required. Please connect your Google account in the admin panel first.',
            'login_required': True,
            'login_url': url_for('google_login.index', _external=True)
        }), 403
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename, {'png', 'jpg', 'jpeg', 'gif', 'webp'}):
        # Create temporary directory for file processing
        temp_dir = os.path.join(current_app.static_folder, 'temp')
        os.makedirs(temp_dir, exist_ok=True)

        # Generate unique filename
        filename = secure_filename(file.filename)
        name, ext = os.path.splitext(filename)
        unique_filename = f"feature_{int(time.time())}{ext}"
        temp_file_path = os.path.join(temp_dir, unique_filename)

        # Save file temporarily
        file.save(temp_file_path)

        # Upload to Google Drive
        from yonca.google_drive_service import authenticate, upload_file, create_view_only_link
        service = authenticate()
        if not service:
            return jsonify({'error': 'Failed to authenticate with Google Drive'}), 500

        try:
            drive_file_id = upload_file(service, temp_file_path, filename)
        except Exception as e:
            print(f"Error uploading to Drive: {e}")
            if "insufficientPermissions" in str(e) or "403" in str(e):
                return jsonify({'error': 'Your Google account does not have sufficient permissions. Please re-link your Google account with full Drive access.'}), 403
            return jsonify({'error': 'Failed to upload file to Google Drive'}), 500
        
        if not drive_file_id:
            return jsonify({'error': 'Failed to upload file to Google Drive'}), 500
        # Set file permissions to make it publicly accessible
        from yonca.google_drive_service import set_file_permissions
        success = set_file_permissions(service, drive_file_id, make_public=True)
        if not success:
            return jsonify({'error': 'Failed to set file permissions'}), 500
        # Create view-only link
        view_link = create_view_only_link(service, drive_file_id, is_image=True)
        if not view_link:
            return jsonify({'error': 'Failed to create view link'}), 500

        # Clean up temporary file
        try:
            os.remove(temp_file_path)
        except:
            pass

        # Return the Google Drive view link
        return jsonify({
            'success': True,
            'image_url': view_link,
            'filename': filename
        })

@api_bp.route('/file/<file_id>')
@login_required
def serve_file(file_id):
    """Serve a Google Drive file after authentication"""
    from yonca.models import CourseAssignmentSubmission, CourseContent, Resource, PDFDocument
    from flask_login import current_user
    from flask import redirect, render_template, url_for
    
    # Find the file in any of the models that store files
    submission = CourseAssignmentSubmission.query.filter_by(drive_file_id=file_id).first()
    course_content = CourseContent.query.filter_by(drive_file_id=file_id).first()
    resource = Resource.query.filter_by(drive_file_id=file_id).first()
    resource_preview = Resource.query.filter_by(preview_drive_file_id=file_id).first()
    pdf_doc = PDFDocument.query.filter_by(drive_file_id=file_id).first()
    
    file_record = submission or course_content or resource or resource_preview or pdf_doc
    
    if not file_record:
        return redirect(url_for('main.index', error='file_not_found'))
    
    # Determine ownership and permissions
    is_owner = False
    is_admin = current_user.is_authenticated and current_user.is_admin
    is_teacher = current_user.is_authenticated and current_user.is_teacher
    is_preview = resource_preview is not None  # Preview images are always public
    is_public = getattr(file_record, 'allow_others_to_view', True)  # Default to True if field doesn't exist
    
    # Check ownership based on file type
    if hasattr(file_record, 'user_id'):
        is_owner = current_user.is_authenticated and file_record.user_id == current_user.id
    elif hasattr(file_record, 'uploaded_by'):
        is_owner = current_user.is_authenticated and file_record.uploaded_by == current_user.id
    
    # Permission logic:
    # 1. Preview images are always public
    # 2. Owner, admin, and teacher always have access
    # 3. For private files (allow_others_to_view=False), only owner/admin/teacher can access
    # 4. For public files, enrolled students (for course content) or anyone can access
    
    if is_preview:
        # Preview images are always accessible
        pass
    elif not is_public:
        if not (is_owner or is_admin or is_teacher):
            return redirect(url_for('main.index', error='auth_required'))
    else:
        # For public course content, check enrollment
        if course_content:
            if current_user.is_authenticated:
                from yonca.models import Course
                course = Course.query.get(course_content.course_id)
                is_enrolled = course and current_user in course.users
                
                if not (is_owner or is_admin or is_teacher or is_enrolled):
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
                              file_id=file_id, 
                              file_title=file_title,
                              file_type=file_type,
                              back_url=back_url,
                              current_user=current_user)

    
    # For other files (submissions, resources, etc.), redirect to the drive_view_link
    if hasattr(file_record, 'drive_view_link') and file_record.drive_view_link:
        return redirect(file_record.drive_view_link)
    
    # If no view link exists, try to construct a direct Google Drive link
    return redirect(f'https://drive.google.com/file/d/{file_id}/view')

@api_bp.route('/import-drive-file', methods=['POST'])
@limiter.limit("5 per 30 seconds")
@login_required
def import_drive_file_endpoint():
    """
    Import a file or folder from Google Drive using full drive scope.
    The file must have been selected via Google Picker for access.
    """
    from yonca.google_drive_service import (
        authenticate, import_drive_file, import_drive_folder
    )
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400
    
    file_id = data.get('file_id')
    file_name = data.get('file_name')
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
        print(f'Error importing file {file_id}: {str(e)}')
        print(traceback.format_exc())
        return jsonify({
            'error': 'Failed to import file',
            'message': str(e)
        }), 500

@api_bp.route('/import-drive-file-to-resource', methods=['POST'])
@limiter.limit("5 per 30 seconds")
@login_required
def import_drive_file_to_resource():
    """
    Import a Google Drive file to create or update a Resource.
    Used when adding files to course resources.
    """
    from yonca.google_drive_service import authenticate, import_drive_file
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400
    
    file_id = data.get('file_id')
    resource_id = data.get('resource_id')  # Optional: if updating existing resource
    
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
        # Import the file from Google Drive
        file_data = import_drive_file(service, file_id)
        
        if isinstance(file_data, dict) and 'error' in file_data:
            return jsonify(file_data), 400
        
        # If updating existing resource
        if resource_id:
            resource = Resource.query.get(resource_id)
            if not resource:
                return jsonify({'error': 'Resource not found'}), 404
            
            # Update resource with imported file data
            resource.name = file_data.get('name')
            resource.drive_file_id = file_data.get('file_id')
            resource.drive_view_link = file_data.get('view_link')
            resource.mime_type = file_data.get('mime_type')
            resource.is_imported = True
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Resource updated with Google Drive file',
                'resource_id': resource.id,
                'file_data': file_data
            }), 200
        else:
            # Create new resource with imported file data
            from yonca.models import Resource
            
            resource = Resource(
                name=file_data.get('name'),
                drive_file_id=file_data.get('file_id'),
                drive_view_link=file_data.get('view_link'),
                mime_type=file_data.get('mime_type'),
                created_by=current_user.id,
                is_imported=True
            )
            
            db.session.add(resource)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'New resource created with Google Drive file',
                'resource_id': resource.id,
                'file_data': file_data
            }), 201
        
    except Exception as e:
        import traceback
        print(f'Error importing file {file_id} to resource: {str(e)}')
        print(traceback.format_exc())
        return jsonify({
            'error': 'Failed to import file to resource',
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
    from yonca.models import CourseContent, CourseContentFolder
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
            
        enrolled = current_user.is_authenticated and (current_user in course.users or current_user.is_teacher or current_user.is_admin)
        if not enrolled:
            return jsonify({'error': 'You must be enrolled in this course to view its contents'}), 403
        
        # Fetch only published contents for this folder with eager loading
        contents = CourseContent.query.filter_by(
            folder_id=folder_id,
            is_published=True
        ).options(
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
                'content_data': content.content_data,
                'drive_file_id': content.drive_file_id,
                'drive_view_link': content.drive_view_link,
                'allow_others_to_view': content.allow_others_to_view,
                'order': content.order,
                'is_published': content.is_published,
                'created_at': content.created_at.isoformat() if content.created_at else None,
                'folder_id': content.folder_id,
                'course_id': content.course_id,
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
        print(f'Error fetching folder contents for folder {folder_id}: {str(e)}')
        print(traceback.format_exc())
        return jsonify({
            'error': 'Failed to fetch folder contents',
            'message': str(e)
        }), 500
