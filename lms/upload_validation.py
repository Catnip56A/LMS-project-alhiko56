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
