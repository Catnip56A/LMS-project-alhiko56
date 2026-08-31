"""
Google Drive service for file uploads and sharing
Build: 2026-04-23T12:45:00Z
"""
import os.path
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from flask import current_app
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)

# drive.file scope: access only files created by the app or opened via the Picker
SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = None  # Upload to root directory for OAuth users

class WorkerCredentials:
    """The actual Phase 4 worker-account identity — a single dedicated Google account's
    OAuth tokens, stored in AppSetting rather than on any User row.

    Duck-types the three attributes authenticate()/refresh_credentials() read and write
    (google_access_token/google_refresh_token/google_token_expiry) so both functions work
    unmodified against this instead of a User. Distinct from the interim Drive Writer
    stopgap above, which just points at an existing admin's own linked account rather than
    storing separate credentials — see setup_checklist.md Phase 4.
    """
    _SETTING_KEYS = {
        'google_access_token': 'worker_google_access_token',
        'google_refresh_token': 'worker_google_refresh_token',
        'google_token_expiry': 'worker_google_token_expiry',
    }

    def _get_setting(self, attr):
        from lms.models import AppSetting
        setting = AppSetting.query.filter_by(key=self._SETTING_KEYS[attr]).first()
        return setting.value if setting else None

    def _set_setting(self, attr, value):
        from lms.models import AppSetting, db
        key = self._SETTING_KEYS[attr]
        setting = AppSetting.query.filter_by(key=key).first()
        if value is None:
            if setting:
                db.session.delete(setting)
            return
        if setting:
            setting.value = value
        else:
            db.session.add(AppSetting(key=key, value=value))

    @property
    def google_access_token(self):
        return self._get_setting('google_access_token')

    @google_access_token.setter
    def google_access_token(self, value):
        self._set_setting('google_access_token', value)

    @property
    def google_refresh_token(self):
        return self._get_setting('google_refresh_token')

    @google_refresh_token.setter
    def google_refresh_token(self, value):
        self._set_setting('google_refresh_token', value)

    @property
    def google_token_expiry(self):
        raw = self._get_setting('google_token_expiry')
        return datetime.fromisoformat(raw) if raw else None

    @google_token_expiry.setter
    def google_token_expiry(self, value):
        self._set_setting('google_token_expiry', value.isoformat() if value else None)


def get_worker_credentials():
    """Return the worker-account credentials if one has actually been linked, else None."""
    creds = WorkerCredentials()
    if not creds.google_access_token:
        return None
    return creds


def clear_worker_credentials():
    """Disconnect the worker account, clearing its stored tokens."""
    creds = WorkerCredentials()
    creds.google_access_token = None
    creds.google_refresh_token = None
    creds.google_token_expiry = None
    from lms.models import db
    db.session.commit()


def get_drive_writer_user():
    """Return the User designated as the system-wide Drive writer, if any.

    Interim stand-in for the Phase 4 worker account: instead of creating a
    dummy Google account to act as a shared service identity (dubious under
    Google's ToS), an admin can designate their own already-linked account as
    the writer everyone's uploads route through. Pointer only — no separate
    token storage, it just reads the designated User's existing OAuth columns.
    """
    from lms.models import AppSetting, User
    setting = AppSetting.query.filter_by(key='drive_writer_user_id').first()
    if not setting or not setting.value:
        return None
    user = User.query.get(int(setting.value))
    if not user or not user.google_access_token:
        return None
    return user


def set_drive_writer(user):
    """Designate `user`'s linked Google account as the system-wide Drive writer."""
    from lms.models import AppSetting, db
    setting = AppSetting.query.filter_by(key='drive_writer_user_id').first()
    if setting:
        setting.value = str(user.id)
    else:
        setting = AppSetting(key='drive_writer_user_id', value=str(user.id))
        db.session.add(setting)
    db.session.commit()


def clear_drive_writer():
    """Remove the designated Drive writer, reverting uploads to per-user OAuth."""
    from lms.models import AppSetting, db
    AppSetting.query.filter_by(key='drive_writer_user_id').delete()
    db.session.commit()


def authenticate(user=None):
    """Authenticate and return the Google Drive service using OAuth tokens.

    When `user` isn't given, resolves in priority order: the real Phase 4 worker account
    (get_worker_credentials), then the interim Drive Writer stopgap (get_drive_writer_user),
    then the current user.
    """
    if user is None:
        user = get_worker_credentials() or get_drive_writer_user()
    if user is None:
        from flask_login import current_user
        user = current_user

    if not user or not user.google_access_token:
        logger.info('No Google OAuth tokens available for user')
        return None

    creds = None
    
    # Check if token is expired and refresh if needed
    if user.google_token_expiry and datetime.utcnow() >= user.google_token_expiry:
        if user.google_refresh_token:
            creds = refresh_credentials(user)
            if not creds:
                # Refresh failed, clear tokens
                logger.error('Token refresh failed, clearing tokens')
                user.google_access_token = None
                user.google_refresh_token = None
                user.google_token_expiry = None
                from lms.models import db
                db.session.commit()
                return None
        else:
            logger.info('Access token expired and no refresh token available')
            # Clear expired token
            user.google_access_token = None
            user.google_refresh_token = None
            user.google_token_expiry = None
            from lms.models import db
            db.session.commit()
            return None
    else:
        creds = Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=current_app.config.get('GOOGLE_CLIENT_ID'),
            client_secret=current_app.config.get('GOOGLE_CLIENT_SECRET'),
            scopes=SCOPES
        )
    
    if creds:
        try:
            # Build service with timeout configuration for large folder operations
            # The timeout parameter sets the request timeout for individual API calls
            service = build(
                'drive', 
                'v3', 
                credentials=creds,
                cache_discovery=False
            )
            
            # Configure the underlying HTTP client timeout
            if hasattr(service, '_http'):
                service._http.timeout = 300  # 5 minutes timeout
                if hasattr(service._http, 'http') and hasattr(service._http.http, 'timeout'):
                    service._http.http.timeout = 300  # Also set on underlying httplib2.Http
            
            logger.info("Google Drive service authenticated successfully using OAuth (with 5min timeout)")
            return service
        except Exception as e:
            logger.error(f'Failed to build Google Drive service: {e}')
            # Clear invalid tokens so user can re-authenticate
            user.google_access_token = None
            user.google_refresh_token = None
            user.google_token_expiry = None
            from lms.models import db
            db.session.commit()
            return None
    else:
        logger.error('Failed to authenticate with Google Drive')
        return None

def get_linked_google_account(user=None):
    """Get information about the linked Google account"""
    if user is None:
        from flask_login import current_user
        user = current_user
    
    if not user or not user.google_access_token:
        return None
    
    # Check if token is expired and refresh if needed
    if user.google_token_expiry and datetime.utcnow() >= user.google_token_expiry:
        if user.google_refresh_token:
            creds = refresh_credentials(user)
            if not creds:
                logger.error('Token refresh failed for account info, clearing tokens')
                from lms.models import db
                user.google_access_token = None
                user.google_refresh_token = None
                user.google_token_expiry = None
                db.session.commit()
                return {'error': 'Token refresh failed'}
        else:
            logger.info('Access token expired and no refresh token available for account info')
            from lms.models import db
            user.google_access_token = None
            user.google_refresh_token = None
            user.google_token_expiry = None
            db.session.commit()
            return {'error': 'Access token expired'}
    
    try:
        # Get user info from Google
        userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {'Authorization': f'Bearer {user.google_access_token}'}
        response = requests.get(userinfo_url, headers=headers)
        response.raise_for_status()
        userinfo = response.json()
        return {
            'email': userinfo.get('email'),
            'name': userinfo.get('name'),
            'token_expiry': user.google_token_expiry.isoformat() if user.google_token_expiry else None,
            'has_refresh_token': bool(user.google_refresh_token)
        }
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            logger.info('Token is invalid (401), clearing tokens')
            from lms.models import db
            user.google_access_token = None
            user.google_refresh_token = None
            user.google_token_expiry = None
            db.session.commit()
            return {'error': 'Invalid or expired token'}
        else:
            logger.error(f'Failed to get Google account info: HTTP {e.response.status_code}')
            return {'error': f'HTTP {e.response.status_code}: {e.response.text}'}
    except Exception as e:
        logger.error(f'Failed to get Google account info: {e}')
        return {'error': str(e)}

def refresh_credentials(user):
    """Refresh expired access token"""
    client_id = current_app.config.get('GOOGLE_CLIENT_ID')
    client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not client_secret or not user.google_refresh_token:
        return None
    
    refresh_data = {
        'grant_type': 'refresh_token',
        'refresh_token': user.google_refresh_token,
        'client_id': client_id,
        'client_secret': client_secret
    }
    
    try:
        response = requests.post('https://oauth2.googleapis.com/token', data=refresh_data)
        response.raise_for_status()
        token_data = response.json()
        
        user.google_access_token = token_data['access_token']
        if 'refresh_token' in token_data:
            user.google_refresh_token = token_data['refresh_token']
        expires_in = token_data.get('expires_in', 3600)
        user.google_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        
        from lms.models import db
        db.session.commit()
        
        return Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES
        )
    except Exception as e:
        logger.error(f'Failed to refresh token: {e}')
        return None

def upload_file(service, file_path, file_name=None, folder_id=None):
    """Upload a file and return its file ID"""
    if file_name is None:
        file_name = os.path.basename(file_path)
    file_metadata = {'name': file_name}
    if folder_id is None:
        folder_id = FOLDER_ID
    if folder_id:
        file_metadata['parents'] = [folder_id]
    media = MediaFileUpload(file_path, resumable=True)
    try:
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True  # required for Shared Drives
        ).execute()
        return uploaded_file['id']
    except HttpError as error:
        logger.error(f'An error occurred: {error}')
        return None

def create_view_only_link(service, file_id, is_image=False):
    """Create a view-only link for files - returns direct Google Drive link"""
    logger.debug(f"create_view_only_link called with file_id={file_id}, is_image={is_image}")
    
    if is_image:
        # For images, return direct Google Drive image link
        view_link = f"https://lh3.googleusercontent.com/d/{file_id}"
        logger.debug(f"Returning image view_link: {view_link}")
        return view_link
    else:
        # For non-images (PDFs, documents), return direct Google Drive viewer link
        view_link = f"https://drive.google.com/file/d/{file_id}/view"
        logger.debug(f"Returning file view_link: {view_link}")
        return view_link

def set_file_permissions(service, file_id, make_public=False, max_retries=3, resource_key=None):
    """Set file permissions on Google Drive file with retry logic and timeout handling.
    `resource_key` is required for files with link-based sharing — see get_file_metadata."""
    import time
    start_time = time.time()

    for attempt in range(max_retries + 1):
        try:
            if make_public:
                # Make file publicly viewable
                permission = {
                    'type': 'anyone',
                    'role': 'reader'
                }
                request = service.permissions().create(
                    fileId=file_id,
                    body=permission,
                    fields='id',
                    supportsAllDrives=True
                )
                if resource_key:
                    request.headers['X-Goog-Drive-Resource-Keys'] = f'{file_id}/{resource_key}'
                request.execute()
                elapsed = time.time() - start_time
                logger.debug(f"File {file_id} made public (took {elapsed:.2f}s)")
                if elapsed > 30:  # Warn if taking more than 30 seconds
                    logger.warning(f"Making file public took {elapsed:.2f}s - approaching timeout limits")
                return True
            else:
                # Remove public permissions to make file private
                try:
                    # Get all permissions for the file
                    permissions = service.permissions().list(fileId=file_id, fields='permissions(id,type)', supportsAllDrives=True).execute()
                    
                    # Delete all 'anyone' permissions
                    for permission in permissions.get('permissions', []):
                        if permission.get('type') == 'anyone':
                            service.permissions().delete(fileId=file_id, permissionId=permission['id'], supportsAllDrives=True).execute()
                            logger.debug(f"Removed public permission from file {file_id}")
                    
                    elapsed = time.time() - start_time
                    logger.debug(f"File {file_id} made private (took {elapsed:.2f}s)")
                    if elapsed > 30:  # Warn if taking more than 30 seconds
                        logger.warning(f"Making file private took {elapsed:.2f}s - approaching timeout limits")
                    return True
                except HttpError as error:
                    logger.error(f'Error removing public permissions: {error}')
                    # If removing fails, still return True to not break the flow
                    logger.debug(f"File {file_id} kept as is (may already be private)")
                    return True
        except HttpError as error:
            elapsed = time.time() - start_time
            logger.error(f'An error occurred setting permissions (attempt {attempt + 1}/{max_retries + 1}, {elapsed:.2f}s): {error}')
            if attempt < max_retries:
                logger.info('Retrying in 1 second...')
                time.sleep(1)
                continue
            return False
        except (ConnectionResetError, ConnectionError, TimeoutError, OSError) as error:
            elapsed = time.time() - start_time
            logger.error(f'Network/timeout error occurred setting permissions for file {file_id} (attempt {attempt + 1}/{max_retries + 1}, {elapsed:.2f}s): {error}')
            if attempt < max_retries:
                # Exponential backoff for timeout errors
                delay = min(2 ** attempt, 10)  # Max 10 seconds delay
                logger.info(f'Retrying in {delay} seconds...')
                time.sleep(delay)
                continue
            logger.debug(f'File {file_id} permissions unchanged due to network/timeout issues after {max_retries + 1} attempts - continuing import')
            return True  # Return True to not break the import flow

def delete_file(service, file_id):
    """Delete a file from Google Drive"""
    try:
        service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        return True
    except HttpError as error:
        logger.error(f'An error occurred: {error}')
        return False

def download_file(service, file_id, local_path, resource_key=None):
    """Download a file from Google Drive to local path. `resource_key` is required for
    link-shared files — see get_file_metadata's docstring for why; without it, downloading a
    Picker-selected, link-shared file 404s even though fetching its metadata succeeded."""
    from googleapiclient.http import MediaIoBaseDownload
    import io

    try:
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        if resource_key:
            request.headers['X-Goog-Drive-Resource-Keys'] = f'{file_id}/{resource_key}'
        with io.FileIO(local_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                logger.info(f"Download {int(status.progress() * 100)}%.")
        return True
    except HttpError as error:
        logger.error(f'An error occurred downloading file: {error}')
        return False

def get_file_metadata(service, file_id, resource_key=None):
    """Get metadata for a Google Drive file. `resource_key` is required for files with
    link-based sharing (type=anyone/domain) — since 2021 Google's Drive API 404s on these
    without it (see https://developers.google.com/workspace/drive/api/guides/resource-keys),
    indistinguishable from a genuine access-denied 404. Picker surfaces it as
    `doc.resourceKey` on picked files."""
    import time
    start_time = time.time()

    try:
        request = service.files().get(
            fileId=file_id,
            fields='id, name, mimeType, size, webViewLink, iconLink',
            supportsAllDrives=True
        )
        if resource_key:
            request.headers['X-Goog-Drive-Resource-Keys'] = f'{file_id}/{resource_key}'
        file = request.execute()
        
        elapsed = time.time() - start_time
        logger.debug(f"get_file_metadata for {file_id} took {elapsed:.2f}s")
        if elapsed > 30:  # Warn if taking more than 30 seconds
            logger.warning(f"get_file_metadata took {elapsed:.2f}s - approaching timeout limits")
        return file
    except HttpError as error:
        elapsed = time.time() - start_time
        if error.resp.status == 404:
            # File not found - log at debug level to avoid cluttering logs
            logger.debug(f"File {file_id} not found (404) after {elapsed:.2f}s")
        else:
            logger.error(f'An error occurred getting file metadata after {elapsed:.2f}s: {error}')
        # Return error information for better handling
        return {'error': str(error), 'error_code': error.resp.status}
    except (ConnectionResetError, ConnectionError, TimeoutError, OSError) as error:
        elapsed = time.time() - start_time
        logger.error(f'Network/timeout error occurred getting file metadata for {file_id} after {elapsed:.2f}s: {error}')
        return {'error': f'Network/timeout error: {str(error)}', 'error_code': 0}
