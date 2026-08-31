"""
API routes for courses, forum, and resources
"""
import math
import os
import re
import requests
from flask import Blueprint, request, jsonify, current_app, redirect, url_for, Response
from flask_login import current_user, login_required
from lms.extensions import limiter
from lms.models import Course, ForumMessage, ForumChannel, Translation, db
from lms.translation_service import translation_service

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
    """Get every channel the current user (or anonymous guest) is allowed to see —
    global channels (the original use of this endpoint), course channels for courses the
    user is enrolled in/manages, and Groups (open ones, or invite-only ones the user
    belongs to). DMs are never listed here — see the (future) dedicated DM endpoint.
    """
    from lms.forum_service import can_view_channel, can_moderate_channel

    channels = ForumChannel.query.filter(
        ForumChannel.is_active.is_(True),
        ForumChannel.channel_type.in_(['global', 'course', 'group']),
    ).order_by(ForumChannel.sort_order, ForumChannel.name).all()

    visible = [c for c in channels if can_view_channel(c, current_user)]

    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'description': c.description,
        'channel_type': c.channel_type,
        'course_id': c.course_id,
        'membership_mode': c.membership_mode,
        'requires_login': c.requires_login,
        'admin_only': c.admin_only,
        'is_public': c.is_public,
        'can_moderate': can_moderate_channel(c, current_user),
    } for c in visible])


@api_bp.route('/forum/dms')
@login_required
def get_dm_channels():
    """List the current user's private conversations — their DM channels, each with the
    other participant's username for display. Not returned by get_forum_channels above,
    which deliberately excludes channel_type='dm' entirely."""
    from lms.models import ForumChannelMembership, User

    memberships = ForumChannelMembership.query.filter_by(user_id=current_user.id).join(
        ForumChannel, ForumChannelMembership.channel_id == ForumChannel.id
    ).filter(ForumChannel.channel_type == 'dm').all()

    result = []
    for m in memberships:
        other = ForumChannelMembership.query.filter(
            ForumChannelMembership.channel_id == m.channel_id,
            ForumChannelMembership.user_id != current_user.id,
        ).first()
        other_user = User.query.get(other.user_id) if other else None
        result.append({
            'channel_id': m.channel_id,
            'slug': m.channel.slug,
            'other_username': other_user.username if other_user else None,
            'other_user_id': other_user.id if other_user else None,
        })
    return jsonify(result)


@api_bp.route('/forum/dms/start', methods=['POST'])
@login_required
def start_dm():
    """Find-or-create a DM channel with another user by username — the "Message this user"
    entry point. Returns the channel slug so the caller can immediately load it."""
    from lms.models import User
    from lms.forum_service import find_or_create_dm

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    if not username:
        return jsonify({'error': 'username is required'}), 400
    if username == current_user.username:
        return jsonify({'error': "You can't message yourself"}), 400

    target = User.query.filter_by(username=username).first()
    if not target:
        return jsonify({'error': 'User not found'}), 404

    channel = find_or_create_dm(current_user, target)
    return jsonify({'success': True, 'slug': channel.slug, 'channel_id': channel.id, 'other_username': target.username}), 200


def _serialize_forum_message(message, current_user_id):
    """Shared JSON shape for a single message — a flat list, not a nested tree. The
    frontend builds both the linear (WhatsApp-style) and nested (Reddit-style) views from
    this same flat, chronologically-ordered list; parent_username/parent_snippet let the
    linear view render an inline reply-quote without a second fetch."""
    parent = message.parent if message.parent_id else None
    is_deleted = message.deleted_at is not None
    return {
        'id': message.id,
        'user_id': message.user_id,
        'username': message.username,
        'message': None if is_deleted else message.message,
        'deleted': is_deleted,
        'timestamp': message.timestamp.isoformat() if message.timestamp else None,
        'parent_id': message.parent_id,
        'parent_username': (parent.username if parent else None),
        'parent_snippet': (parent.message[:80] if parent and parent.message and not parent.deleted_at else None),
        'pinned': message.pinned,
        'is_current_user': current_user_id is not None and message.user_id == current_user_id,
    }


@api_bp.route('/forum/messages')
def get_forum_messages():
    """Get every message in one channel, as a flat chronological list (see
    _serialize_forum_message for why — the frontend builds both reply-view modes from this
    one shape)."""
    from lms.forum_service import can_view_channel

    channel_slug = request.args.get('channel', 'general')
    channel = ForumChannel.query.filter_by(slug=channel_slug, is_active=True).first()
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    if not can_view_channel(channel, current_user):
        return jsonify({'error': 'Access denied for this channel'}), 403

    messages = (
        ForumMessage.query.filter_by(channel_id=channel.id)
        .order_by(ForumMessage.timestamp.asc(), ForumMessage.id.asc())
        .all()
    )
    current_user_id = current_user.id if current_user.is_authenticated else None

    return jsonify({
        'channel': channel.slug,
        'channel_id': channel.id,
        'channel_name': channel.name,
        'channel_type': channel.channel_type,
        'requires_login': channel.requires_login,
        'messages': [_serialize_forum_message(m, current_user_id) for m in messages],
    })

@api_bp.route('/forum/messages', methods=['POST'])
def post_forum_message():
    """Post a new forum message or reply"""
    from lms.forum_service import can_post_to_channel

    data = request.get_json()
    if not data or 'message' not in data or not data['message'].strip():
        return jsonify({'error': 'Message required'}), 400

    channel_slug = data.get('channel', 'general')
    channel = ForumChannel.query.filter_by(slug=channel_slug, is_active=True).first()
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    if not can_post_to_channel(channel, current_user):
        return jsonify({'error': 'Access denied for this channel'}), 403

    parent_id = data.get('parent_id')
    if parent_id:
        parent = ForumMessage.query.filter_by(id=parent_id, channel_id=channel.id).first()
        if not parent:
            return jsonify({'error': 'Parent message not found in this channel'}), 404

    if not current_user.is_authenticated:
        # Anonymous posting only ever reaches here for a channel with requires_login=False
        # (can_post_to_channel already enforced that) — course/group/dm channels always
        # require login, so this branch is unreachable for them.
        username = data.get('username', '').strip()
        if not username:
            return jsonify({'error': 'Username required for anonymous posting'}), 400
        new_message = ForumMessage(username=username, message=data['message'], parent_id=parent_id, channel_id=channel.id)
    else:
        new_message = ForumMessage(
            user_id=current_user.id, username=current_user.username,
            message=data['message'], parent_id=parent_id, channel_id=channel.id,
        )

    db.session.add(new_message)
    db.session.commit()
    db.session.refresh(new_message)

    return jsonify({'success': True, **_serialize_forum_message(new_message, current_user.id if current_user.is_authenticated else None)}), 201

@api_bp.route('/forum/messages/<int:message_id>', methods=['PUT'])
@login_required
def edit_forum_message(message_id):
    """Edit a forum message (only by its author — moderators can pin/delete but not rewrite
    someone else's words)."""
    message = ForumMessage.query.get_or_404(message_id)

    if message.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    if message.deleted_at:
        return jsonify({'error': 'Cannot edit a deleted message'}), 400

    data = request.get_json()
    if not data or 'message' not in data or not data['message'].strip():
        return jsonify({'error': 'Message required'}), 400

    message.message = data['message']
    db.session.commit()

    return jsonify({'success': True}), 200

@api_bp.route('/forum/messages/<int:message_id>', methods=['DELETE'])
@login_required
def delete_forum_message(message_id):
    """Soft-delete a forum message (owner or a moderator of its channel) — the row stays so
    reply threads don't orphan, rendered client-side as a "[message deleted]" placeholder."""
    from datetime import datetime
    from lms.forum_service import can_moderate_channel

    message = ForumMessage.query.get_or_404(message_id)
    is_owner = message.user_id == current_user.id
    if not (is_owner or can_moderate_channel(message.forum_channel, current_user)):
        return jsonify({'error': 'Unauthorized'}), 403

    message.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'success': True}), 200


@api_bp.route('/forum/messages/<int:message_id>/pin', methods=['POST'])
@login_required
def pin_forum_message(message_id):
    """Pin/unpin a message — moderator-only. Not offered for DMs (see can_moderate_channel)."""
    from lms.forum_service import can_moderate_channel

    message = ForumMessage.query.get_or_404(message_id)
    if not can_moderate_channel(message.forum_channel, current_user):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json(silent=True) or {}
    message.pinned = bool(data.get('pinned', True))
    db.session.commit()

    return jsonify({'success': True, 'pinned': message.pinned}), 200


@api_bp.route('/forum/messages/<int:message_id>/translate', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def translate_forum_message(message_id):
    """Translate one message on demand — no new persistence, the existing Translation table
    already caches by (source_text, target_language) regardless of where the text came from."""
    from lms.forum_service import can_view_channel

    message = ForumMessage.query.get_or_404(message_id)
    if not can_view_channel(message.forum_channel, current_user):
        return jsonify({'error': 'Access denied'}), 403
    if message.deleted_at:
        return jsonify({'error': 'Message was deleted'}), 400

    target_language = (request.get_json(silent=True) or {}).get('target_language', '').strip()
    if not target_language:
        return jsonify({'error': 'target_language is required'}), 400

    translated = translation_service.get_translation(message.message, target_language)
    return jsonify({'success': True, 'translated_text': translated}), 200


@api_bp.route('/forum/channels/<int:channel_id>/clear', methods=['POST'])
@login_required
@limiter.limit("5 per hour")
def clear_forum_channel(channel_id):
    """Hard-delete every message in a channel — the moderator "clear history" (per-call, not
    time-based) action. Relies on ForumMessage.parent_id's ON DELETE CASCADE so replies of a
    deleted top-level message don't need to be walked/deleted individually."""
    from lms.forum_service import can_moderate_channel

    channel = ForumChannel.query.get_or_404(channel_id)
    if not can_moderate_channel(channel, current_user):
        return jsonify({'error': 'Unauthorized'}), 403

    top_level = ForumMessage.query.filter_by(channel_id=channel.id, parent_id=None).all()
    count = ForumMessage.query.filter_by(channel_id=channel.id).count()
    for message in top_level:
        db.session.delete(message)
    db.session.commit()

    return jsonify({'success': True, 'deleted': count}), 200

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


def _r2_or_drive_media_url(*, r2_key, drive_file_id, fallback_name=None, download=False, r2_preview_key=None):
    """R2-vs-Drive URL resolution for CourseAssignmentSubmission — the same precedence
    _content_media_url uses for CourseContent (R2 wins when set, Drive's single generic
    download/preview pair is the fallback for rows not yet migrated), factored out separately
    since CourseAssignmentSubmission doesn't share CourseContent's shape (no `.title`, and
    Drive never needed type-specific URLs — e.g. the image/audio branches — here, since
    submissions were never rendered in an iframe the way CourseContent was)."""
    from lms import r2_client

    if not download and r2_preview_key:
        return r2_client.generate_presigned_url(r2_preview_key)

    if r2_key:
        disposition = None
        if download:
            # Same key shape as CourseContent's (r2_client.build_content_key) — see
            # _content_media_url's comment for why this slices rather than splits on '-'.
            basename = r2_key.rsplit('/', 1)[-1]
            original_name = basename[33:] if len(basename) > 33 and basename[32] == '-' else (fallback_name or 'download')
            disposition = f'attachment; filename="{original_name}"'
        return r2_client.generate_presigned_url(r2_key, disposition=disposition)

    if drive_file_id:
        if download:
            return f'https://drive.google.com/uc?export=download&id={drive_file_id}'
        return f'https://drive.google.com/file/d/{drive_file_id}/preview'

    return None


@api_bp.route('/file/s/<int:submission_id>')
@login_required
def serve_submission_by_db_id(submission_id):
    """Serve an assignment submission by its database ID — the R2-aware sibling of serve_file
    for CourseAssignmentSubmission, needed because an R2-only row (submitted after the R2
    migration) has no drive_file_id for serve_file's URL scheme to key off, mirroring why
    serve_content_by_db_id exists for CourseContent."""
    from lms.models import CourseAssignmentSubmission

    submission = CourseAssignmentSubmission.query.get(submission_id)
    if not submission:
        return redirect(url_for('main.index', error='file_not_found'))

    course = submission.assignment.course if submission.assignment else None
    is_owner = current_user.is_authenticated and submission.user_id == current_user.id
    is_admin = current_user.is_authenticated and current_user.is_admin
    is_manager = course.is_managed_by(current_user) if course else False
    # Pre-existing permission shape, preserved as-is (not tightened or loosened here): a
    # submission with allow_others_to_view=True (the default set by submit_assignment) is
    # viewable by any authenticated user, not just the owner/course manager or classmates —
    # the legacy serve_file route already allowed exactly this for submissions.
    is_public = submission.allow_others_to_view
    if not (is_owner or is_admin or is_manager or (is_public and current_user.is_authenticated)):
        return redirect(url_for('main.index', error='auth_required'))

    url = _r2_or_drive_media_url(
        r2_key=submission.r2_key,
        r2_preview_key=submission.r2_preview_key,
        drive_file_id=submission.drive_file_id,
    )
    if not url:
        return redirect(url_for('main.index', error='file_not_found'))
    return redirect(url)


@api_bp.route('/file/<file_id>')
@login_required
def serve_file(file_id):
    """Serve a Google Drive file after authentication"""
    from lms.models import CourseAssignmentSubmission, CourseContent, Course
    from flask_login import current_user
    from flask import redirect, render_template, url_for

    # Find the file in any of the models that store files
    submission = CourseAssignmentSubmission.query.filter_by(drive_file_id=file_id).first()
    course_content = CourseContent.query.filter_by(drive_file_id=file_id).first()

    file_record = submission or course_content

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


    # For other files (submissions, etc.), redirect to the drive_view_link
    # Note: this route looks records up by drive_file_id, so R2-only CourseContent rows
    # never reach it and no template links course content here — it's now legacy-only for
    # CourseContent, still live for any not-yet-migrated CourseAssignmentSubmission row
    # (submit_assignment/serve_submission_by_db_id are the current path for new submissions).
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


@api_bp.route('/course/<int:course_id>/upload-content', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def upload_course_content(course_id):
    """Queue a multi-file course-content upload as a background job — replaces both the old
    synchronous single-file upload_file form action and the removed Picker-import-from-Drive
    feature's bulk-import role (see the "Picker import replaced" checklist entry). Deliberately
    flat, unlike Picker's old folder import: every file lands directly in the chosen target
    folder, no subfolder structure is recreated, per an explicit scope decision. Multiple
    files, each potentially needing a LibreOffice conversion and an R2 upload, could otherwise
    hold a gunicorn worker for real time — the same reasoning behind this session's async
    job-queue conversion elsewhere. See _execute_bulk_upload_content_job (job_manager.py) for
    the work itself, and upload_course_content_status below for the poll side.
    """
    from lms.models import Course
    from lms.upload_validation import validate_upload, UploadValidationError
    from werkzeug.utils import secure_filename
    import uuid

    course = Course.query.get(course_id)
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    if not course.is_managed_by(current_user):
        return jsonify({'error': 'forbidden'}), 403

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files provided'}), 400

    folder_id = request.form.get('folder_id') or None
    title = (request.form.get('title') or '').strip()
    description = (request.form.get('description') or '').strip()
    published = request.form.get('published') in ('true', 'True', '1', 'on')
    allow_view = request.form.get('allow_view') in ('true', 'True', '1', 'on')

    from lms.routes import UPLOAD_STAGING_DIR
    os.makedirs(UPLOAD_STAGING_DIR, exist_ok=True)

    # Validate every file before staging any of them — rejects the whole batch on the first
    # bad file with simple, predictable semantics rather than a partial upload.
    for f in files:
        try:
            validate_upload(f, max_bytes=current_app.config['MAX_CONTENT_LENGTH'])
        except UploadValidationError as e:
            return jsonify({'error': f'{f.filename}: {e}'}), 400

    staged = []
    try:
        for f in files:
            filename = secure_filename(f.filename) or 'file'
            temp_path = os.path.join(UPLOAD_STAGING_DIR, f'{uuid.uuid4().hex}_{filename}')
            f.save(temp_path)
            staged.append({'staged_path': temp_path, 'original_filename': f.filename})
    except Exception:
        for item in staged:
            try:
                os.remove(item['staged_path'])
            except OSError:
                pass
        raise

    job_data = {
        'course_id': course.id,
        'folder_id': folder_id,
        'title': title,
        'description': description,
        'published': published,
        'allow_view': allow_view,
        'files': staged,
    }

    from lms.job_manager import job_manager
    job_id = job_manager.queue_job('bulk_upload_content', job_data)

    return jsonify({'success': True, 'job_id': job_id}), 202


@api_bp.route('/course/<int:course_id>/upload-content/status/<job_id>', methods=['GET'])
@login_required
def upload_course_content_status(course_id, job_id):
    """Poll side of the background upload job queued by upload_course_content."""
    from lms.job_manager import job_manager, JobStatus
    job = job_manager.get_job(job_id)
    job_data = job.data if job else None
    if not job or job.type != 'bulk_upload_content' or not job_data or job_data.get('course_id') != course_id:
        return jsonify({'error': 'Job not found'}), 404

    from lms.models import Course
    course = Course.query.get(course_id)
    if not course or not course.is_managed_by(current_user):
        return jsonify({'error': 'Job not found'}), 404

    if job.status == JobStatus.COMPLETED:
        return jsonify({'success': True, 'status': 'completed', **(job.result or {})}), 200
    if job.status == JobStatus.FAILED:
        return jsonify({'success': False, 'status': 'failed', 'error': job.error or 'Upload failed.'}), 200
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
