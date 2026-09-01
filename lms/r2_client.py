"""
Thin S3-compatible client for Cloudflare R2 — no Flask/DB dependency, same role as
gemini_client.py/core_translator.py play for their own external services. Course-content
byte storage; runtime orchestration (uploads, serving, RAG downloads) lives in
routes/api.py, routes/__init__.py, and rag_service.py.

Credentials are read inline via os.environ.get at point of use, not centralized into
Config — Config is reserved for values templates/JS need, which R2 secrets never are.

A second, optional "upstream" client can be configured (R2_UPSTREAM_*) pointing at the
production bucket with a read-only token. This exists purely for dev: pulling the
production/staging DB into dev (`just db-pull-staging`) brings in `r2_key` values that
only exist in the production bucket, and without this fallback that content would 403
locally until re-uploaded. generate_presigned_url() and download_file() both fall back to
it automatically when the primary bucket doesn't have the object.
"""
import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import datetime
from urllib.parse import quote

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

DEFAULT_URL_EXPIRY_SECONDS = 21600  # 6h
WORKER_URL_EXPIRY_SECONDS = 60  # short-lived signed token for the Cloudflare Worker proxy

_client_cache = {}


def _env(name, default=''):
    return os.environ.get(name, default) or default


def is_configured() -> bool:
    return bool(_env('R2_ACCOUNT_ID') and _env('R2_ACCESS_KEY_ID') and _env('R2_SECRET_ACCESS_KEY') and _env('R2_BUCKET_NAME'))


def _is_upstream_configured() -> bool:
    return bool(
        _env('R2_UPSTREAM_ACCOUNT_ID') and _env('R2_UPSTREAM_ACCESS_KEY_ID')
        and _env('R2_UPSTREAM_SECRET_ACCESS_KEY') and _env('R2_UPSTREAM_BUCKET_NAME')
    )


def _build_client(account_id, access_key_id, secret_access_key):
    return boto3.client(
        's3',
        endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name='auto',
        config=BotoConfig(signature_version='s3v4', retries={'max_attempts': 3, 'mode': 'standard'}),
    )


def _client():
    """Lazily build and memoize the primary R2 client. None if not configured."""
    if not is_configured():
        return None
    if 'primary' not in _client_cache:
        _client_cache['primary'] = _build_client(_env('R2_ACCOUNT_ID'), _env('R2_ACCESS_KEY_ID'), _env('R2_SECRET_ACCESS_KEY'))
    return _client_cache['primary']


def _upstream_client():
    """Lazily build and memoize the optional read-only upstream (prod) client. None if not configured."""
    if not _is_upstream_configured():
        return None
    if 'upstream' not in _client_cache:
        _client_cache['upstream'] = _build_client(
            _env('R2_UPSTREAM_ACCOUNT_ID'), _env('R2_UPSTREAM_ACCESS_KEY_ID'), _env('R2_UPSTREAM_SECRET_ACCESS_KEY'),
        )
    return _client_cache['upstream']


def _bucket() -> str:
    return _env('R2_BUCKET_NAME')


def _upstream_bucket() -> str:
    return _env('R2_UPSTREAM_BUCKET_NAME')


def _url_expiry() -> int:
    try:
        return int(_env('R2_URL_EXPIRY_SECONDS', str(DEFAULT_URL_EXPIRY_SECONDS)))
    except ValueError:
        return DEFAULT_URL_EXPIRY_SECONDS


def build_content_key(course_id, filename, when: datetime | None = None) -> str:
    """Build a stable, unique, debuggable object key. Pure function, no network — safe to
    call before the file exists anywhere, and reused by both upload paths and the backfill
    script so keys look the same regardless of origin.
    """
    when = when or datetime.now()
    name = secure_filename(filename or '') or 'file'
    if len(name) > 120:
        base, dot, ext = name.rpartition('.')
        if dot and len(ext) <= 10:
            name = base[:120 - len(ext) - 1] + '.' + ext
        else:
            name = name[:120]
    return f'courses/{course_id}/{when.strftime("%Y")}/{when.strftime("%m")}/{uuid.uuid4().hex}-{name}'


def build_forum_attachment_key(channel_id, filename, when: datetime | None = None) -> str:
    """Same shape as build_content_key but channel-scoped, for chat/forum message attachments."""
    when = when or datetime.now()
    name = secure_filename(filename or '') or 'file'
    if len(name) > 120:
        base, dot, ext = name.rpartition('.')
        if dot and len(ext) <= 10:
            name = base[:120 - len(ext) - 1] + '.' + ext
        else:
            name = name[:120]
    return f'forum/{channel_id}/{when.strftime("%Y")}/{when.strftime("%m")}/{uuid.uuid4().hex}-{name}'


def upload_file(local_path: str, key: str, content_type: str | None = None, filename: str | None = None) -> bool:
    client = _client()
    if client is None:
        logger.error('R2 not configured; cannot upload_file')
        return False
    extra_args = {}
    if content_type:
        extra_args['ContentType'] = content_type
    if filename:
        extra_args['ContentDisposition'] = f'inline; filename="{filename}"'
    try:
        client.upload_file(local_path, _bucket(), key, ExtraArgs=extra_args or None)
        return True
    except (ClientError, BotoCoreError, OSError) as e:
        logger.error(f'R2 upload_file error for key {key}: {e}')
        return False


def download_file(key: str, dest_path: str) -> bool:
    client = _client()
    if client is not None:
        try:
            client.download_file(_bucket(), key, dest_path)
            return True
        except (ClientError, BotoCoreError, OSError) as e:
            logger.info(f'R2 download_file miss on primary bucket for key {key}: {e}')
    upstream = _upstream_client()
    if upstream is None:
        return False
    try:
        upstream.download_file(_upstream_bucket(), key, dest_path)
        return True
    except (ClientError, BotoCoreError, OSError) as e:
        logger.error(f'R2 download_file error for key {key}: {e}')
        return False


def _head_object(key: str, *, upstream: bool = False) -> dict | None:
    client = _upstream_client() if upstream else _client()
    bucket = _upstream_bucket() if upstream else _bucket()
    if client is None:
        return None
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey'):
            return None
        logger.error(f'R2 head_object error for key {key}: {e}')
        return None
    except BotoCoreError as e:
        logger.error(f'R2 head_object error for key {key}: {e}')
        return None


def object_exists(key: str, *, upstream: bool = False) -> bool:
    return _head_object(key, upstream=upstream) is not None


def get_object_size(key: str, *, upstream: bool = False) -> int | None:
    head = _head_object(key, upstream=upstream)
    return head.get('ContentLength') if head else None


def generate_presigned_url(key: str, expires_in: int | None = None, disposition: str | None = None, response_content_type: str | None = None) -> str | None:
    """Sign a GET URL for `key`. Tries the primary bucket first; if the object isn't there
    and an upstream (read-only prod) client is configured, falls back to presigning against
    that bucket instead — see module docstring. Local signing only, no network round trip,
    cheap enough to call on every embed request.
    """
    params_extra = {}
    if disposition:
        params_extra['ResponseContentDisposition'] = disposition
    if response_content_type:
        params_extra['ResponseContentType'] = response_content_type

    client = _client()
    if client is not None and object_exists(key):
        try:
            return client.generate_presigned_url(
                'get_object', Params={'Bucket': _bucket(), 'Key': key, **params_extra}, ExpiresIn=expires_in or _url_expiry(),
            )
        except (ClientError, BotoCoreError) as e:
            logger.error(f'R2 generate_presigned_url error for key {key}: {e}')

    upstream = _upstream_client()
    if upstream is not None:
        try:
            return upstream.generate_presigned_url(
                'get_object', Params={'Bucket': _upstream_bucket(), 'Key': key, **params_extra}, ExpiresIn=expires_in or _url_expiry(),
            )
        except (ClientError, BotoCoreError) as e:
            logger.error(f'R2 generate_presigned_url (upstream) error for key {key}: {e}')

    if client is None and upstream is None:
        logger.error('R2 not configured; cannot generate_presigned_url')
    return None


def _worker_base_url() -> str | None:
    return _env('R2_WORKER_URL') or None


def _worker_secret() -> str | None:
    return _env('R2_WORKER_SIGNING_SECRET') or None


def generate_worker_url(key: str, *, download: bool = False, filename: str | None = None, expires_in: int | None = None) -> str | None:
    """Sign a short-lived URL for the Cloudflare Worker fronting R2 (see workers/file-proxy/).

    Unlike generate_presigned_url (a raw AWS SigV4 bearer URL good for hours, and one that
    reveals the R2 host to the client), this token is valid for `expires_in` seconds only —
    the Worker validates the HMAC then streams the object itself, so the R2 host/credentials
    never reach the browser. Returns None if the worker isn't configured, so callers should
    fall back to generate_presigned_url in that case (see get_media_url).
    """
    base = _worker_base_url()
    secret = _worker_secret()
    if not base or not secret:
        return None
    exp = int(time.time()) + (expires_in or WORKER_URL_EXPIRY_SECONDS)
    dl = '1' if download else '0'
    fname = filename or ''
    message = f'{key}:{exp}:{dl}:{fname}'
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    query = f'exp={exp}&sig={sig}&dl={dl}'
    if fname:
        query += f'&filename={quote(fname)}'
    return f'{base.rstrip("/")}/{quote(key)}?{query}'


def get_media_url(key: str, *, download: bool = False, filename: str | None = None, disposition: str | None = None) -> str | None:
    """Preferred way to hand a client a URL for an R2 object's bytes: the signed Worker proxy
    when configured, else a plain presigned URL (also the fallback for anything only present
    in the upstream/prod bucket — see module docstring — since the Worker only binds the
    primary bucket). `disposition` is only used on the presigned-URL fallback path; the Worker
    derives its own Content-Disposition from `download`/`filename` instead.
    """
    if object_exists(key):
        worker_url = generate_worker_url(key, download=download, filename=filename)
        if worker_url:
            return worker_url
    return generate_presigned_url(key, disposition=disposition)


def delete_object(key: str) -> bool:
    client = _client()
    if client is None:
        logger.error('R2 not configured; cannot delete_object')
        return False
    try:
        client.delete_object(Bucket=_bucket(), Key=key)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.error(f'R2 delete_object error for key {key}: {e}')
        return False
