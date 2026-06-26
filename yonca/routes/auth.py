"""
Authentication routes
"""
from flask import Blueprint, request, redirect, url_for, flash, render_template, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from markupsafe import Markup
from yonca.models import User, db, HomeContent
import logging
import requests
import secrets
import os
from datetime import datetime, timedelta


def _resolve_oauth_base_url():
    """Select OAuth base URL from the current request host."""
    try:
        host = (request.host or '').lower()
        scheme = request.scheme or 'https'
    except RuntimeError:
        host = ''
        scheme = 'https'

    if 'staging' in host:
        return 'https://staging.yonca-sdc.com'
    if host.startswith('localhost') or host.startswith('127.0.0.1') or 'local.yonca-sdc.com' in host:
        return f"{scheme}://{host}"
    if host:
        return 'https://yonca-sdc.com'

    # Fallback for CLI/tasks where request context is unavailable.
    uri = os.environ.get('GOOGLE_REDIRECT_URI')
    if not uri:
        raise RuntimeError("GOOGLE_REDIRECT_URI environment variable is not set")
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    return f"{parsed.scheme}://{parsed.netloc}"

def get_google_redirect_uri(redirect_uri=None):
    if redirect_uri:
        return redirect_uri
    return f"{_resolve_oauth_base_url()}/auth/google/callback"

def get_google_link_uri():
    return f"{_resolve_oauth_base_url()}/auth/google/link"

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    # Check if login page is limited (only for GET requests to show the login page)
    if request.method == 'GET':
        from yonca.routes import check_page_limitation
        limitation_redirect = check_page_limitation('login')
        if limitation_redirect:
            return limitation_redirect
    
    # Removed: Google OAuth callback handling - using link account for logged-in users only
    # code = request.args.get('code')
    # state = request.args.get('state')
    # error = request.args.get('error')
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin_login = request.form.get('admin_login') == 'on'
        
        user = User.query.filter_by(username=username).first()
        
        # Rate limiting: check if user has exceeded login attempts
        if user:
            now = datetime.utcnow()
            time_since_last_attempt = (now - user.last_attempt_time).total_seconds() if user.last_attempt_time else float('inf')
            
            # Reset attempts if more than 30 seconds have passed
            if time_since_last_attempt > 30:
                user.login_attempts = 0
            
            # Check if user has exceeded rate limit
            if user.login_attempts >= 5 and time_since_last_attempt <= 30:
                remaining_time = int(30 - time_since_last_attempt)
                flash(f'Too many login attempts. Please wait {remaining_time} seconds before trying again.')
                logging.warning(f"Rate limit exceeded for user: {username}")
                return render_template('login.html')
        
        if user and user.check_password(password):
            # Reset login attempts on successful login
            user.login_attempts = 0
            user.last_attempt_time = None
            # Check if there's a pending Google account link
            from flask import session
            pending_link = session.pop('pending_google_link', None)
            
            if pending_link:
                # Check if this Google account is already linked to another user
                google_email = pending_link['email']
                existing_linked_user = User.query.filter(
                    User.google_access_token.isnot(None),
                    User.email == google_email
                ).first()
                
                if existing_linked_user and existing_linked_user.id != user.id:
                    flash(Markup(
                        f'{_("Google account")} ({google_email}) {_("is already linked to another user account.")}'
                        f'<br><small>{_("If you proceed, the connection of this Google account to the other Yonca account will be")} <em><strong>{_("rewritten")}</strong></em> {_("with the account you enter.")}</small>'
                    ))
                    logging.warning(f"Attempted to link Google account {google_email} to {username}, but already linked to user ID {existing_linked_user.id}")
                else:
                    # Link the Google account to this user
                    user.google_access_token = pending_link['access_token']
                    user.google_refresh_token = pending_link['refresh_token']
                    user.google_token_expiry = datetime.utcnow() + timedelta(seconds=pending_link['expires_in'])
                    
                    # Update email if not set or different
                    if not user.email or user.email != pending_link['email']:
                        # Check if email is already used by another user
                        existing_user = User.query.filter_by(email=pending_link['email']).first()
                        if not existing_user or existing_user.id == user.id:
                            user.email = pending_link['email']
                    
                    db.session.commit()
                    logging.info(f"Google account linked for user: {username}")
                    flash(f'Google account ({pending_link["email"]}) successfully linked!')
            
            login_user(user)
            logging.info(f"User {username} logged in successfully")
            
            db.session.commit()
            
            # Check if admin login is requested and user is admin
            if admin_login and user.is_admin:
                return redirect('/admin')
            else:
                return redirect(url_for('main.index'))
        elif user:
            # Track failed login attempt
            user.login_attempts += 1
            user.last_attempt_time = datetime.utcnow()
            db.session.commit()
            logging.warning(f"Failed login attempt for username: {username} - incorrect password (attempt {user.login_attempts})")
        else:
            logging.warning(f"Failed login attempt for non-existent username: {username}")
        
        flash('Invalid username or password')
    
    home_content = HomeContent.query.filter_by(is_active=True).first() or HomeContent()
    return render_template('login.html', home_content=home_content)

@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    logging.info(f"User {current_user.username} logged out")
    logout_user()
    # Redirect with cache-busting parameter to ensure fresh session check
    return redirect(url_for('main.index', logout_time=int(datetime.utcnow().timestamp())))

# Removed: Google OAuth login route - using link account for logged-in users only
# @auth_bp.route('/login/google')
# def login_google():
#     """Redirect to Google OAuth login"""
#     ...

@auth_bp.route('/link-google-account')
def link_google_account():
    """Initiate Google OAuth flow to link existing account"""
    client_id = current_app.config.get('GOOGLE_CLIENT_ID')
    if not client_id:
        flash('Google OAuth not configured')
        return redirect(url_for('auth.login'))
    
    redirect_uri = get_google_link_uri()
    
    scope = 'openid email profile https://www.googleapis.com/auth/drive.file'
    state = secrets.token_urlsafe(32)  # Generate a secure state
    # Store state in session for verification
    from flask import session
    session['oauth_state'] = state
    session['oauth_redirect_uri'] = redirect_uri  # Store redirect URI for callback
    session['oauth_action'] = 'link'  # Mark this as a linking action
    
    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope={scope}&"
        f"state={state}&"
        f"access_type=offline&prompt=consent"
    )
    return redirect(auth_url)

@auth_bp.route('/auth/google/link')
def google_link_callback():
    """Handle Google OAuth callback for account linking"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    from flask import session
    stored_state = session.pop('oauth_state', None)
    oauth_action = session.pop('oauth_action', None)
    
    if error:
        flash(f'OAuth error: {error}')
        return redirect(url_for('auth.login'))
    
    if not code or state != stored_state or oauth_action != 'link':
        flash('Invalid OAuth callback')
        return redirect(url_for('auth.login'))
    
    client_id = current_app.config.get('GOOGLE_CLIENT_ID')
    client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET')
    
    # Use the same redirect URI as used in link_google_account (stored in session)
    redirect_uri = session.pop('oauth_redirect_uri', None)
    if not redirect_uri:
        redirect_uri = get_google_link_uri()
    
    # Exchange code for access token
    token_url = 'https://oauth2.googleapis.com/token'
    token_data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    try:
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        refresh_token = token_json.get('refresh_token')
        expires_in = token_json.get('expires_in', 3600)
        
        if not access_token:
            flash('Failed to obtain access token')
            return redirect(url_for('auth.login'))
        
        # Get user info
        userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {'Authorization': f'Bearer {access_token}'}
        userinfo_response = requests.get(userinfo_url, headers=headers)
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
        
        google_email = userinfo.get('email')
        
        if not google_email:
            flash('Failed to get user email from Google')
            return redirect(url_for('auth.login'))
        
        # Check if this Google account is already linked to another user
        existing_linked_user = User.query.filter(
            User.google_access_token.isnot(None),
            User.email == google_email
        ).first()
        
        if existing_linked_user:
            flash(Markup(
                f'{_("Google account")} ({google_email}) {_("is already linked to another user account. Please use a different Google account.")}'
                f'<br><small>{_("If you proceed, the connection of this Google account to the other Yonca account will be")} <em><strong>{_("rewritten")}</strong></em> {_("with the account you enter.")}</small>'
            ))
            logging.warning(f"Attempted to link Google account {google_email} which is already linked to user ID {existing_linked_user.id}")
            return redirect(url_for('auth.login'))
        
        # Store credentials temporarily in session for linking
        session['pending_google_link'] = {
            'email': google_email,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': expires_in
        }
        
        flash(f'Google account ({google_email}) is ready to link. Please login with your existing account.')
        return redirect(url_for('auth.login'))
    
    except requests.RequestException as e:
        logging.error(f'OAuth token exchange failed: {e}')
        flash('OAuth authentication failed')
        return redirect(url_for('auth.login'))

@auth_bp.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    from flask import session
    stored_state = session.pop('oauth_state', None)
    
    if error:
        flash(f'OAuth error: {error}')
        return redirect(url_for('auth.login'))
    
    if not code or state != stored_state:
        flash('Invalid OAuth callback')
        return redirect(url_for('auth.login'))
    
    client_id = current_app.config.get('GOOGLE_CLIENT_ID')
    client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET')
    
    redirect_uri = get_google_redirect_uri()
    
    # Exchange code for access token
    token_url = 'https://oauth2.googleapis.com/token'
    token_data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    }
    
    try:
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        refresh_token = token_json.get('refresh_token')
        expires_in = token_json.get('expires_in', 3600)
        
        if not access_token:
            flash('Failed to obtain access token')
            return redirect(url_for('auth.login'))
        
        # Get user info
        userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {'Authorization': f'Bearer {access_token}'}
        userinfo_response = requests.get(userinfo_url, headers=headers)
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
        
        email = userinfo.get('email')
        name = userinfo.get('name')
        
        if not email:
            flash('Failed to get user email from Google')
            return redirect(url_for('auth.login'))
        
        # Find or create user
        user = User.query.filter_by(email=email).first()
        if not user:
            # Create new user for OAuth login
            # Generate a dummy password since OAuth users don't need one
            dummy_password = secrets.token_hex(32)
            username = name.replace(' ', '_').lower()  # Simple username from name
            # Ensure unique username
            base_username = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}_{counter}"
                counter += 1
            
            user = User(username=username, email=email, password=dummy_password)
            db.session.add(user)
            db.session.commit()
            logging.info(f"New user created via Google OAuth: {username} ({email})")
        else:
            logging.info(f"Existing user logged in via Google OAuth: {user.username} ({email})")
        
        # Store Google tokens
        user.google_access_token = access_token
        user.google_refresh_token = refresh_token
        user.google_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        db.session.commit()
        
        login_user(user)
        # Redirect to next URL if stored, otherwise to main page
        from flask import session
        next_url = session.pop('next_url', None)
        if next_url:
            return redirect(next_url)
        return redirect(url_for('main.index'))
    
    except requests.RequestException as e:
        logging.error(f'OAuth token exchange failed: {e}')
        flash('OAuth authentication failed')
        return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow the logged-in user to change their password."""
    home_content = HomeContent.query.filter_by(is_active=True).first() or HomeContent()

    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash(_('Current password is incorrect.'))
            return render_template('change_password.html', home_content=home_content)

        if len(new_password) < 6:
            flash(_('New password must be at least 6 characters long.'))
            return render_template('change_password.html', home_content=home_content)

        if new_password != confirm_password:
            flash(_('New passwords do not match.'))
            return render_template('change_password.html', home_content=home_content)

        current_user.password = new_password
        db.session.commit()
        logging.info(f"User {current_user.username} changed their password")
        flash(_('Password changed successfully.'))
        return redirect(url_for('main.index'))

    return render_template('change_password.html', home_content=home_content)


@auth_bp.route('/google-account-info')
@login_required
def google_account_info():
    """Display information about the linked Google account"""
    from yonca.google_drive_service import get_linked_google_account
    
    account_info = get_linked_google_account(current_user)
    
    if account_info and 'error' not in account_info:
        return render_template('google_account_info.html', account_info=account_info)
    else:
        error = account_info.get('error', 'No Google account linked') if account_info else 'No Google account linked'
        return render_template('google_account_info.html', error=error)
