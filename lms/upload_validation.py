"""
Upload content validation — checks real file content (magic bytes) rather than
trusting the filename extension alone. No Flask/DB dependency.
"""
import filetype

# Mirrors the file types this app already knows how to handle (see add_file_emoji's
# mime_to_ext map in lms/__init__.py) plus common archive formats used for course content.
ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/svg+xml', 'image/webp',
    'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm',
    'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/mp4',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/zip', 'application/x-rar-compressed', 'application/x-rar',
    'image/vnd.adobe.photoshop',
}

# Formats with no reliable magic-byte signature — allowed through on extension alone.
TEXT_LIKE_EXTENSIONS = {'txt', 'csv', 'json', 'xml'}

IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/svg+xml', 'image/webp'}
PDF_MIME_TYPES = {'application/pdf'}


class UploadValidationError(ValueError):
    """Raised when an uploaded file's real content doesn't match what's expected."""


def _detect_mime(file_storage):
    """Sniff the real MIME type from the file's magic bytes, leaving the stream position unchanged."""
    head = file_storage.stream.read(261)
    file_storage.stream.seek(0)
    kind = filetype.guess(head)
    return kind.mime if kind else None


def content_type_for_mime(mime):
    """Map a known MIME string to a CourseContent.content_type.

    Shared by the upload path (which sniffs bytes) and the Drive-import path (which gets
    an authoritative mimeType from Drive's own metadata), so both agree on what counts as
    a transcribable lecture.
    """
    if mime and (mime.startswith('video/') or mime.startswith('audio/')):
        return 'video'
    return 'file'


def detect_course_content_type(file_storage):
    """Map an upload to a CourseContent.content_type by sniffing its real bytes.

    Returns 'video' for video/audio (the types the RAG pipeline transcribes), else 'file'.
    Sniffed rather than read off the filename because content titles are freeform display
    names — the same reason _extract_drive_file_text and _transcribe_video stopped trusting
    them. Without this, an uploaded lecture lands as content_type='file' and is never
    transcribed, silently indexing as 0 chunks.
    """
    return content_type_for_mime(_detect_mime(file_storage))


def detect_mime_and_content_type(file_storage):
    """Sniff both the real MIME type and its CourseContent.content_type in one pass —
    the upload path needs both (MIME for R2's ContentType/file_mime_type column, content_type
    for the row itself) and calling detect_course_content_type + _detect_mime separately would
    sniff the same bytes twice."""
    mime = _detect_mime(file_storage)
    return mime, content_type_for_mime(mime)


def validate_upload(file_storage, max_bytes=None, expected_mimes=None):
    """
    Validate an uploaded werkzeug FileStorage by real content, not just its filename.
    `expected_mimes`, if given, narrows the allowed set beyond ALLOWED_MIME_TYPES
    (e.g. IMAGE_MIME_TYPES for a preview image field).
    Raises UploadValidationError with a user-facing message if the upload should be rejected.
    """
    if max_bytes is not None:
        file_storage.stream.seek(0, 2)  # seek to end
        size = file_storage.stream.tell()
        file_storage.stream.seek(0)
        if size > max_bytes:
            raise UploadValidationError(f'File is too large (max {max_bytes // (1024 * 1024)} MB).')

    allowed = expected_mimes if expected_mimes is not None else ALLOWED_MIME_TYPES
    detected_mime = _detect_mime(file_storage)

    if detected_mime is not None:
        if detected_mime not in allowed:
            raise UploadValidationError('This file type is not allowed.')
        return

    # No magic-byte signature detected (e.g. plain text) — fall back to extension,
    # but only for the general (non-narrowed) allowlist, since text has no image/pdf signature.
    if expected_mimes is not None:
        raise UploadValidationError('Could not verify this file\'s content type.')
    filename = file_storage.filename or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in TEXT_LIKE_EXTENSIONS:
        raise UploadValidationError('Could not verify this file\'s content type.')
