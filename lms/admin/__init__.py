"""
Admin interface views and configuration
"""
import os
import secrets
import requests
from datetime import datetime, timedelta
from flask import flash, redirect, url_for, request, current_app, session
from flask_admin import Admin, AdminIndexView, expose, BaseView
from flask_admin.contrib.sqla import ModelView
from markupsafe import Markup
from wtforms import Form, FileField, StringField, TextAreaField, BooleanField
from wtforms.validators import Optional, DataRequired
from flask_login import current_user
from flask_wtf import FlaskForm


def _resolve_oauth_base_url():
    """Select OAuth base URL from the current request host."""
    try:
        host = (request.host or '').lower()
        scheme = request.scheme or 'https'
    except RuntimeError:
        host = ''
        scheme = 'https'

    if 'staging' in host:
        return 'https://staging.yourdomain.example.com'
    if host.startswith('localhost') or host.startswith('127.0.0.1') or 'local.yourdomain.example.com' in host:
        return f"{scheme}://{host}"
    if host:
        return 'https://yourdomain.example.com'

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
    return f"{_resolve_oauth_base_url()}/admin/google_login/"
from lms.models import User, Course, ForumMessage, ForumChannel, MoxoTest, Resource, db, SiteSettings, CourseContent, ContentView

ADMIN_PERMISSIONS = [
    ('user_management',        'User Management'),
    ('course_management',      'Course Management'),
    ('certificate_management', 'Certificate Management'),
    ('forum_management',       'Forum Management'),
    ('builder_management',     'Builder Management'),
    ('moxo_test_management',   'Moxo Test Management'),
    ('resource_management',    'Resource Management'),
]

class AdminIndexView(AdminIndexView):
    """Custom admin index view with authentication and home content management"""
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.any_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    def render(self, template, **kwargs):
        """Override render to ensure admin_base_template is set"""
        if 'admin_base_template' not in kwargs:
            try:
                base_template = self.admin.theme.base_template
            except AttributeError:
                base_template = 'admin/base.html'
            kwargs['admin_base_template'] = base_template
        return super().render(template, **kwargs)

    @expose('/', methods=['GET', 'POST'])
    def index(self):
        if not current_user.is_authenticated or not current_user.any_admin:
            return redirect(url_for('auth.login'))
        if not current_user.has_perm('builder_management'):
            return self.render('admin/subadmin_home.html')

        site_settings = SiteSettings.query.filter_by(is_active=True).first()
        if not site_settings:
            site_settings = SiteSettings()
            db.session.add(site_settings)
            db.session.commit()

        form = SiteSettingsForm()

        if request.method == 'POST':
            site_settings = SiteSettings.query.filter_by(is_active=True).first()
            if not site_settings:
                flash('Error: No active site settings found.', 'error')
                return redirect(url_for('admin.index'))

            db.session.add(site_settings)
            form = SiteSettingsForm(request.form)

            if form.validate():
                site_settings.site_name = form.site_name.data
                site_settings.site_logo_url = form.site_logo_url.data
                site_settings.contact_info = {
                    'whatsapp': form.contact_whatsapp.data,
                    'email': form.contact_email.data,
                    'address': form.contact_address.data,
                }
                site_settings.is_active = True
                db.session.commit()
                flash('Site settings updated successfully!', 'success')
                return redirect(url_for('admin.index'))
            else:
                flash('Please fill in all required fields.', 'error')

        form.site_name.data = site_settings.site_name
        form.site_logo_url.data = site_settings.site_logo_url
        contact_info = site_settings.contact_info or {}
        form.contact_whatsapp.data = contact_info.get('whatsapp', '')
        form.contact_email.data = contact_info.get('email', '')
        form.contact_address.data = contact_info.get('address', '')

        return self.render('admin/index.html', form=form, site_settings=site_settings)

class SecureModelView(ModelView):
    """Base model view — subclasses set `permission` to gate by a specific permission key."""
    permission = None

    def is_accessible(self):
        if not current_user.is_authenticated:
            return False
        if self.permission:
            return current_user.has_perm(self.permission)
        return current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

class LogoutView(BaseView):
    """Custom logout view for admin interface"""
    
    @expose('/')
    def index(self):
        from flask_login import logout_user
        logout_user()
        flash('You have been logged out successfully.')
        return redirect(url_for('auth.login'))
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.any_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

class GoogleLoginView(BaseView):
    """Custom view for Google OAuth login to get Drive access tokens"""
    
    @expose('/')
    def index(self):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('auth.login'))
        
        # Handle Google OAuth callback if code is present
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if code or error:
            stored_state = session.pop('oauth_state', None)
            
            if error:
                flash(f'OAuth error: {error}')
                return redirect(url_for('google_login.index'))
            
            if not code or state != stored_state:
                flash('Invalid OAuth callback')
                return redirect(url_for('google_login.index'))
            
            client_id = current_app.config.get('GOOGLE_CLIENT_ID')
            client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET')
            
            # Use the same redirect URI as used in connect (stored in session)
            redirect_uri = session.pop('oauth_redirect_uri', get_google_redirect_uri())
            
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
                    return redirect(url_for('google_login.index'))
                
                # Store Google tokens for the current user
                current_user.google_access_token = access_token
                current_user.google_refresh_token = refresh_token
                current_user.google_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
                db.session.commit()
                
                flash('Google Drive connected successfully!', 'success')
                return redirect(url_for('admin.index'))
            
            except requests.RequestException as e:
                print(f'OAuth token exchange failed: {e}')
                flash('OAuth authentication failed')
                return redirect(url_for('google_login.index'))
        
        # Check if user already has Google tokens
        if current_user.google_access_token:
            # Test if the tokens actually work
            from lms.google_drive_service import authenticate
            test_service = authenticate(current_user)
            if test_service:
                flash('You are already connected to Google Drive.', 'info')
                return redirect(url_for('admin.index'))
            else:
                # Tokens are invalid, clear them and allow re-connection
                current_user.google_access_token = None
                current_user.google_refresh_token = None
                current_user.google_token_expiry = None
                db.session.commit()
                flash('Your Google Drive connection was invalid. Please reconnect.', 'warning')
        
        # Show Google login page
        return self.render('admin/google_login.html')
    
    @expose('/connect')
    def connect(self):
        if not current_user.is_authenticated or not current_user.is_admin:
            print("DEBUG: User not authenticated or not admin, redirecting to login")
            return redirect(url_for('auth.login'))
        
        print(f"DEBUG: Admin Google connect called for user {current_user.username}")
        
        try:
            # Redirect to Google OAuth with next parameter to return to admin
            # Use configurable redirect URI
            redirect_uri = get_google_redirect_uri()
            
            print(f"DEBUG: Admin OAuth - request.host={request.host}, GOOGLE_REDIRECT_URI={os.environ.get('GOOGLE_REDIRECT_URI')}, redirect_uri={redirect_uri}")
            
            # Build the OAuth URL manually to ensure correct redirect URI
            client_id = current_app.config.get('GOOGLE_CLIENT_ID')
            if not client_id:
                print("DEBUG: No GOOGLE_CLIENT_ID configured")
                flash('Google OAuth not configured')
                return redirect(url_for('admin.index'))
                
            scope = 'openid email profile https://www.googleapis.com/auth/drive'
            state = secrets.token_urlsafe(32)
            session['oauth_state'] = state
            session['oauth_redirect_uri'] = redirect_uri  # Store redirect URI for callback
            session['next_url'] = url_for('admin.index')
            
            auth_url = (
                f"https://accounts.google.com/o/oauth2/auth?"
                f"response_type=code&"
                f"client_id={client_id}&"
                f"redirect_uri={redirect_uri}&"
                f"scope={scope}&"
                f"state={state}&"
                f"access_type=offline&prompt=consent"
            )
            
            print(f"DEBUG: Redirecting to Google OAuth: {auth_url}")
            return redirect(auth_url)
            
        except Exception as e:
            print(f"DEBUG: Error in admin Google connect: {e}")
            flash(f'Error connecting to Google: {str(e)}')
            return redirect(url_for('google_login.index'))
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

class CourseManagementView(BaseView):
    """Custom view for managing course pages"""
    
    @expose('/')
    def index(self):
        if not current_user.is_authenticated or not current_user.has_perm('course_management'):
            return redirect(url_for('auth.login'))

        # Fetch all courses
        courses = Course.query.all()
        return self.render('admin/course_management.html', courses=courses)

    @expose('/course/<int:course_id>')
    def analytics(self, course_id):
        """Viewing-time analytics for a single course"""
        if not current_user.is_authenticated or not current_user.has_perm('course_management'):
            return redirect(url_for('auth.login'))

        course = Course.query.get_or_404(course_id)

        # ── Enrolled users ────────────────────────────────────────────────────
        users = sorted(course.users, key=lambda u: u.username.lower())
        user_list = [{'id': u.id, 'username': u.username} for u in users]

        # ── All course content items (tracked by DB id, not Drive file id) ─────
        contents = (CourseContent.query
                    .filter_by(course_id=course_id)
                    .order_by(CourseContent.order, CourseContent.id)
                    .all())

        file_list = []
        total_per_user = {}
        selected_user_id = request.args.get('user_id', type=int)

        for cc in contents:
            content_db_id = str(cc.id)   # ContentView.content_id stores the DB id as a string
            file_title = cc.title

            # ── Aggregate views for this content item across all enrolled users ─
            rows = (db.session.query(
                        ContentView.user_id,
                        db.func.sum(ContentView.viewing_duration).label('total_dur'),
                        db.func.count(ContentView.id).label('view_count'))
                    .filter(
                        ContentView.content_type == 'course_content',
                        ContentView.content_id == content_db_id,
                        ContentView.user_id.in_([u.id for u in users]))
                    .group_by(ContentView.user_id)
                    .all())

            views_per_user = {}
            for r in rows:
                dur = int(r.total_dur or 0)
                cnt = int(r.view_count or 0)
                views_per_user[r.user_id] = {'duration': dur, 'count': cnt}
                total_per_user[r.user_id] = total_per_user.get(r.user_id, 0) + dur

            file_list.append({
                'file_id':    cc.id,
                'file_title': file_title,
                'views_per_user': views_per_user,
            })

        # sort files alphabetically
        file_list.sort(key=lambda x: x['file_title'].lower())

        # ── Colour scale ──────────────────────────────────────────────────────
        # Use predefined list of 100 distinct colors
        color_list = [
            "#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231", "#911EB4", "#42D4F4", "#F032E6", "#BFEF45", "#FABED4",
            "#469990", "#DCBEFF", "#9A6324", "#FFFAC8", "#800000", "#AAFFC3", "#808000", "#FFD8B1", "#000075", "#FF6F61",
            "#40E0D0", "#4B0082", "#FFD700", "#FA8072", "#DA70D6", "#87CEEB", "#228B22", "#FF6347", "#6A5ACD", "#FF1493",
            "#2E8B57", "#1E90FF", "#FF69B4", "#C71585", "#4682B4", "#F4A460", "#BDB76B", "#9370DB", "#20B2AA", "#CD853F",
            "#D2691E", "#FF8C00", "#00FF7F", "#7FFFD4", "#B22222", "#9400D3", "#7CFC00", "#F08080", "#00BFFF", "#BC8F8F",
            "#5F9EA0", "#9ACD32", "#DDA0DD", "#E9967A", "#3CB371", "#6495ED", "#EE82EE", "#00CED1", "#BA55D3", "#98FB98",
            "#CD5C5C", "#7851A9", "#CCFF00", "#CC5500", "#E30B5C", "#007BA7", "#FFBF00", "#50C878", "#E0115F", "#0F52BA",
            "#00A86B", "#FFDB58", "#C54B8C", "#005F99", "#8DB600", "#FF7518", "#FF00FF", "#007FFF", "#7FFF00", "#E34234",
            "#614051", "#0047AB", "#8A9A5B", "#F28500", "#FF007F", "#5DADEC", "#93C572", "#B87333", "#FF6EC7", "#1560BD",
            "#4F7942", "#FFCBA4", "#FF77FF", "#4F42B5", "#8EE53F", "#FD5E53", "#C8A2C8", "#99FFFF", "#7BB661", "#FF2400"
        ]
        max_total = max((total_per_user.get(u.id, 0) for u in users), default=0)
        user_colors = {}
        for idx, u in enumerate(users):
            # Assign color from list, cycle if more users than colors
            user_colors[u.id] = color_list[idx % len(color_list)]

        site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
        return self.render('admin/course_analytics.html',
                    course=course,
                    users=users,
                    user_list=user_list,
                    files=file_list,
                    total_per_user=total_per_user,
                    selected_user_id=selected_user_id,
                    max_total=max_total,
                    user_colors=user_colors,
                    site_settings=site_settings)
    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_perm('course_management')

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

class SiteSettingsForm(FlaskForm):
    """Form for editing basic site branding settings"""
    site_name = StringField('Site Name', [Optional()], default="LMS")
    site_logo_url = StringField('Site Logo URL', [Optional()], default="")
    contact_whatsapp = StringField('Contact WhatsApp', [Optional()], default="")
    contact_email = StringField('Contact Email', [Optional()], default="info@example.com")
    contact_address = StringField('Contact Address', [Optional()], default="")

class UserView(SecureModelView):
    """Admin view for User model with password management"""
    permission = 'user_management'
    column_list = ('id', 'username', 'email', 'first_name', 'last_name', 'city', 'is_admin', 'courses')
    column_searchable_list = ['username', 'email', 'first_name', 'last_name', 'city']
    form_columns = ('username', 'email', 'first_name', 'last_name', 'city', 'is_admin', 'is_teacher', 'courses', 'new_password')
    form_excluded_columns = ('_password', 'password')
    column_formatters = {
        'courses': lambda v, c, m, p: ', '.join([course.title for course in m.courses]) if m.courses else 'None'
    }

    form_extra_fields = {
        'new_password': StringField('New Password', [Optional()], description='Leave blank to keep current password')
    }

    form_widget_args = {
        'city': {'data-city-input': True}
    }

    extra_js = ['/static/js/city_autocomplete.js']
    column_filters = ('city', 'created_at')

    create_template = 'admin/user_create_edit.html'
    edit_template = 'admin/user_create_edit.html'
    list_template = 'admin/user_list.html'

    def on_model_change(self, form, model, is_created):
        """Handle password changes during model creation/update"""
        if form.new_password.data:
            model.password = form.new_password.data
        return super(UserView, self).on_model_change(form, model, is_created)

class CourseForm(FlaskForm):
    """Form for editing course with dropdown menu management"""
    title = StringField('Title', [DataRequired()])
    description = TextAreaField('Description', [Optional()])
    time_slot = StringField('Time Slot', [Optional()])
class CourseView(SecureModelView):
    """Admin view for Course model"""
    permission = 'course_management'
    column_list = ('id', 'title', 'description', 'time_slot', 'users')
    column_searchable_list = ['title', 'description']
    form = CourseForm
    column_formatters = {
        'users': lambda v, c, m, p: ', '.join([user.username for user in m.users]) if m.users else 'None'
    }

    @expose('/edit/', methods=['GET', 'POST'])
    def edit_view(self, id=None, url=None):
        """Custom edit view for course core fields"""
        if not current_user.is_authenticated or not current_user.has_perm('course_management'):
            return redirect(url_for('auth.login'))

        # Get id from request args if not provided
        if id is None:
            id = request.args.get('id')

        course = self.get_one(id)
        if not course:
            return redirect(url_for('admin.index'))

        if request.method == 'POST':
            # Handle form submission
            course.title = request.form.get('title', '')
            course.description = request.form.get('description', '')
            course.time_slot = request.form.get('time_slot', '')

            # Parse tags from comma-separated input — only overwrite if field was non-empty
            tags_input = request.form.get('tags', '').strip()
            if tags_input:
                course.tags = [tag.strip() for tag in tags_input.split(',') if tag.strip()]

            db.session.commit()

            # Automatically translate the course content
            try:
                from lms.content_translator import auto_translate_course
                auto_translate_course(course)
                db.session.commit()
                print(f"Auto-translated course: {course.title}")
            except Exception as e:
                print(f"Warning: Failed to auto-translate course {course.id}: {str(e)}")

            flash('Course updated successfully!', 'success')
            return redirect(url_for('admin.index'))

        # For editing, we need to show the original English text, not translated versions
        # Create a dict with English versions of translatable fields
        from lms.content_translator import get_translated_content
        english_course_data = {
            'id': course.id,
            'title': get_translated_content('course', course.id, 'title', course.title, 'en') or course.title,
            'description': get_translated_content('course', course.id, 'description', course.description, 'en') or course.description,
            'time_slot': course.time_slot,
        }

        return self.render('admin/course_edit.html', course=english_course_data)

    @expose('/new/', methods=['GET', 'POST'])
    def create_view(self):
        """Custom create view for course core fields"""
        if not current_user.is_authenticated or not current_user.has_perm('course_management'):
            return redirect(url_for('auth.login'))

        if request.method == 'POST':
            # Parse tags from comma-separated input
            tags_input = request.form.get('tags', '').strip()
            tags = [tag.strip() for tag in tags_input.split(',') if tag.strip()] if tags_input else []

            course = Course(
                title=request.form.get('title', ''),
                description=request.form.get('description', ''),
                time_slot=request.form.get('time_slot', ''),
                tags=tags,
            )

            db.session.add(course)
            db.session.commit()

            # Automatically translate the new course content
            try:
                from lms.content_translator import auto_translate_course
                auto_translate_course(course)
                db.session.commit()
                print(f"Auto-translated new course: {course.title}")
            except Exception as e:
                print(f"Warning: Failed to auto-translate new course {course.id}: {str(e)}")

            flash('Course created successfully!', 'success')
            return redirect(url_for('admin.index'))

        return self.render('admin/course_edit.html', course=None)

class ResourceForm(Form):
    """Custom form for resource creation with file upload"""
    title = StringField('Title', [DataRequired()])
    description = TextAreaField('Description')
    tags = StringField('Tags')  # Space-separated tags
    preview_image = FileField('Preview Image')  # Optional preview image upload
    file = FileField('File')  # Optional file upload
    access_pin = StringField('Access PIN', render_kw={'readonly': True, 'style': 'background-color: #f8f9fa;'})
    is_active = BooleanField('Active', default=True)

class ResourceView(SecureModelView):
    """Admin view for Resource model with file upload"""
    permission = 'resource_management'
    column_list = ('id', 'title', 'description', 'tags', 'drive_view_link', 'access_pin', 'pin_expires_at', 'pin_last_reset', 'uploaded_by', 'upload_date', 'is_active', 'reset_pin_button')
    column_searchable_list = ['title', 'description', 'tags']
    form = ResourceForm
    form_excluded_columns = ('uploaded_by', 'upload_date', 'drive_file_id', 'drive_view_link', 'pin_expires_at', 'pin_last_reset', 'preview_image')
    
    # Enable file uploads
    form_enctype = 'multipart/form-data'
    
    column_formatters = dict(
        reset_pin_button=lambda v, c, m, p: Markup(f'<a href="/admin/resource/reset_pin/{m.id}" class="btn btn-sm btn-warning"><i class="fa fa-refresh"></i> Reset PIN</a>'),
        access_pin=lambda v, c, m, p: Markup(f'<code style="font-size: 14px; background: #f8f9fa; padding: 2px 6px; border-radius: 3px;">{m.access_pin}</code>') if m.access_pin else 'Not generated',
        pin_expires_at=lambda v, c, m, p: m.pin_expires_at.strftime('%Y-%m-%d %H:%M:%S') if m.pin_expires_at else 'N/A',
        pin_last_reset=lambda v, c, m, p: m.pin_last_reset.strftime('%Y-%m-%d %H:%M:%S') if m.pin_last_reset else 'N/A'
    )
    
    @expose('/reset_pin/<int:resource_id>')
    def reset_pin(self, resource_id):
        """Reset the PIN for a specific resource"""
        from flask import flash, redirect, url_for
        
        resource = self.model.query.get_or_404(resource_id)
        old_pin = resource.access_pin
        resource.reset_pin()
        self.session.commit()
        
        flash(f'PIN reset successfully. New PIN: {resource.access_pin} (was: {old_pin})', 'success')
        return redirect(url_for('resource.index_view'))
    
    def on_model_change(self, form, model, is_created):
        """Handle file upload when model is created or changed"""
        if is_created:
            # Ensure PIN is generated for new resources
            if not model.access_pin:
                model.generate_new_pin()
            
            # Handle preview image upload
            preview_file = form.preview_image.data
            if preview_file:
                from werkzeug.utils import secure_filename
                import os
                import random
                from flask import flash
                from lms.google_drive_service import authenticate, upload_file, create_view_only_link
                
                try:
                    # Create temporary directory
                    temp_dir = os.path.join(current_app.static_folder, 'temp')
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    # Generate secure filename
                    filename = secure_filename(preview_file.filename)
                    unique_filename = f"preview_{random.randint(1000, 9999)}_{filename}"
                    temp_file_path = os.path.join(temp_dir, unique_filename)
                    
                    # Save file temporarily
                    preview_file.save(temp_file_path)
                    
                    # Upload to Google Drive
                    service = authenticate()
                    if not service:
                        flash('Failed to authenticate with Google Drive. Preview image not uploaded.', 'error')
                    else:
                        drive_file_id = upload_file(service, temp_file_path, filename)
                        if drive_file_id:
                            # Create view-only link for image
                            view_link = create_view_only_link(service, drive_file_id, is_image=True)
                            if view_link:
                                model.preview_image = view_link
                            else:
                                flash('Failed to create preview image view link.', 'error')
                        else:
                            flash('Failed to upload preview image to Google Drive.', 'error')
                    
                    # Clean up temporary file
                    try:
                        os.remove(temp_file_path)
                    except:
                        pass
                        
                except Exception as e:
                    flash(f'Error uploading preview image: {str(e)}', 'error')
            
            # Handle file upload for new models
            file = form.file.data
            if file:
                from werkzeug.utils import secure_filename
                import os
                import random
                from flask import flash
                from lms.google_drive_service import authenticate, upload_file, create_view_only_link
                
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
                    service = authenticate()
                    if not service:
                        flash('Failed to authenticate with Google Drive. File not uploaded.', 'error')
                    else:
                        drive_file_id = upload_file(service, temp_file_path, filename)
                        if drive_file_id:
                            # Create view-only link
                            view_link = create_view_only_link(service, drive_file_id, is_image=False)
                            if view_link:
                                model.drive_file_id = drive_file_id
                                model.drive_view_link = view_link
                            else:
                                flash('Failed to create view link.', 'error')
                        else:
                            flash('Failed to upload file to Google Drive.', 'error')
                    
                    # Clean up temporary file
                    try:
                        os.remove(temp_file_path)
                    except:
                        pass
                        
                except Exception as e:
                    flash(f'Error uploading file: {str(e)}', 'error')
        
        return super().on_model_change(form, model, is_created)
    
    def create_form(self):
        """Override form creation to ensure no extra fields"""
        form = super(ResourceView, self).create_form()
        return form
    
    def edit_form(self, obj):
        """Override edit form - no file upload for editing"""
        form = super(ResourceView, self).edit_form(obj)
        # Remove file field from edit form since we don't support re-uploading
        if hasattr(form, 'file'):
            delattr(form, 'file')
        if hasattr(form, 'preview_image'):
            delattr(form, 'preview_image')
        return form

class MoxoTestView(SecureModelView):
    """Admin view for MoxoTest model"""
    permission = 'moxo_test_management'
    column_list = ('id', 'user_id', 'result', 'timestamp')
    column_searchable_list = ['result']
    form_excluded_columns = ('timestamp',)

class ForumChannelView(SecureModelView):
    """Admin view for ForumChannel model"""
    permission = 'forum_management'
    column_list = ('name', 'slug', 'description', 'requires_login', 'admin_only', 'is_active', 'sort_order', 'created_at')
    column_searchable_list = ['name', 'slug', 'description']
    column_filters = ['requires_login', 'admin_only', 'is_active']
    form_columns = ('name', 'slug', 'description', 'requires_login', 'admin_only', 'is_active', 'sort_order')
    form_excluded_columns = ('created_at', 'updated_at')

    def on_model_change(self, form, model, is_created):
        """Ensure slug is URL-friendly"""
        if hasattr(model, 'slug') and model.slug:
            # Make slug URL-friendly
            model.slug = model.slug.lower().replace(' ', '-').replace('_', '-')
        return super().on_model_change(form, model, is_created)

    def delete_model(self, model):
        """Override delete to prevent deletion of 'general' channel and move messages"""
        if model.slug == 'general':
            flash('Cannot delete the General Discussion channel.', 'error')
            return False
        
        # Move all messages from this channel to 'general'
        messages_to_move = ForumMessage.query.filter_by(channel=model.slug).all()
        for message in messages_to_move:
            message.channel = 'general'
        db.session.commit()
        
        # Proceed with deletion
        return super().delete_model(model)

class ForumMessageView(SecureModelView):
    """Admin view for ForumMessage model"""
    permission = 'forum_management'


class TranslateContentView(BaseView):
    """View for translating all content with one click"""

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_perm('builder_management')

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))
    
    @expose('/')
    def index(self):
        """Default view - redirect to home"""
        return redirect(url_for('admin.index'))
    
    @expose('/translate-content', methods=['POST'])
    def translate_content(self):
        """Queue a translation job and return immediately"""
        from flask import jsonify
        from lms.job_manager import job_manager

        if not self.is_accessible():
            return jsonify({'success': False, 'error': 'Admin access required'}), 403

        # Queue the translation job
        job_id = job_manager.queue_job(
            job_type='translate_content',
            job_data={}
        )

        return jsonify({
            'success': True,
            'message': 'Translation job queued successfully',
            'job_id': job_id
        })

    @expose('/job-status/<job_id>')
    def job_status(self, job_id):
        """Get the status of a background job"""
        from flask import jsonify
        from lms.job_manager import job_manager

        if not self.is_accessible():
            return jsonify({'success': False, 'error': 'Admin access required'}), 403

        job = job_manager.get_job(job_id)
        if not job:
            return jsonify({'success': False, 'error': 'Job not found'}), 404

        return jsonify({
            'success': True,
            'job': job.to_dict()
        })

    @expose('/delete-translations', methods=['POST'])
    def delete_translations(self):
        """Delete all translations for Russian"""
        from flask import jsonify
        
        if not self.is_accessible():
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        try:
            from lms.models import ContentTranslation, Translation
            from lms.constants import SUPPORTED_LANGUAGES
            
            # Count translations before deletion
            ru_content_count = ContentTranslation.query.filter_by(target_language='ru').count()
            ru_cache_count = Translation.query.filter_by(target_language='ru').count()
            
            total_before = ru_content_count + ru_cache_count
            
            # Delete from ContentTranslation table
            ContentTranslation.query.filter(ContentTranslation.target_language.in_(['az', 'ru'])).delete()
            
            # Delete from Translation cache table
            Translation.query.filter(Translation.target_language.in_(['az', 'ru'])).delete()
            
            db.session.commit()
            
            message = f"Deleted {total_before} total translations ({ru_content_count + ru_cache_count} Russian)."
            
            return jsonify({'success': True, 'message': message, 'stats': {
                'ru_content_translations': ru_content_count,
                'ru_cache_translations': ru_cache_count,
                'total_deleted': total_before
            }})
            
        except Exception as e:
            from flask import jsonify
            import traceback
            error_details = traceback.format_exc()
            print(f"Delete translations error: {error_details}")
            return jsonify({'success': False, 'error': str(e)}), 500

class CertificateTuningView(BaseView):
    """Admin view for per-course certificate overlay tuning."""

    def is_accessible(self):
        return current_user.is_authenticated and current_user.has_perm('certificate_management')

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    @staticmethod
    def _parse_tuning(form, defaults):
        def _f(key):
            return float(form.get(key, defaults.get(key, 0)))
        return {
            'y_name':         _f('y_name'),
            'font_name_size': _f('font_name_size'),
            'name_color': [
                int(form.get('name_color_r', 30)),
                int(form.get('name_color_g', 30)),
                int(form.get('name_color_b', 80)),
            ],
            'course_label':    (form.get('course_label') or '').strip(),
            'x_course':        _f('x_course'),
            'y_course':        _f('y_course'),
            'font_course_size': _f('font_course_size'),
            'course_color': [
                int(form.get('course_color_r', 40)),
                int(form.get('course_color_g', 40)),
                int(form.get('course_color_b', 40)),
            ],
            'x_meta':   _f('x_meta'),
            'y_date':   _f('y_date'),
            'date_color': [
                int(form.get('date_color_r', 40)),
                int(form.get('date_color_g', 40)),
                int(form.get('date_color_b', 40)),
            ],
            'x_cert_id':  _f('x_cert_id'),
            'y_cert_id':  _f('y_cert_id'),
            'cert_id_color': [
                int(form.get('cert_id_color_r', 40)),
                int(form.get('cert_id_color_g', 40)),
                int(form.get('cert_id_color_b', 40)),
            ],
            'x_qr':    _f('x_qr'),
            'y_qr':    _f('y_qr'),
            'qr_size': _f('qr_size'),
            'template_file': os.path.basename(form.get('template_file', '') or ''),
        }

    @expose('/template-image/<filename>')
    def template_image(self, filename):
        """Serve a template thumbnail from TEMPLATE_DIR."""
        import re
        from flask import send_file, abort as _abort
        from lms.certificate_generator import TEMPLATE_DIR, _IMAGE_EXTS
        if not re.fullmatch(r'[\w\-. ]+', filename) or \
                os.path.splitext(filename)[1].lower() not in _IMAGE_EXTS:
            _abort(400)
        path = os.path.join(TEMPLATE_DIR, filename)
        if os.path.isfile(path):
            return send_file(path)
        _abort(404)

    @expose('/preview', methods=['POST'])
    def preview(self):
        from flask import Response
        from lms.certificate_generator import generate_preview_bytes, _DEFAULTS
        values = self._parse_tuning(request.form, _DEFAULTS)
        try:
            png = generate_preview_bytes(values)
            return Response(png, mimetype='image/png')
        except FileNotFoundError as e:
            return str(e), 404

    @expose('/remove-override', methods=['POST'])
    def remove_override(self):
        import json as _json
        from lms.certificate_generator import TUNING_PATH
        course_id = request.form.get('course_id', '')
        if course_id and course_id != 'default':
            try:
                with open(TUNING_PATH, encoding='utf-8') as f:
                    data = _json.load(f)
            except (OSError, _json.JSONDecodeError):
                data = {}
            if course_id in data:
                del data[course_id]
                with open(TUNING_PATH, 'w', encoding='utf-8') as f:
                    _json.dump(data, f, indent=2)
            flash('Override removed. Course will now use default tuning.', 'success')
        return redirect(url_for('certificate_tuning.index'))

    @expose('/', methods=['GET', 'POST'])
    def index(self):
        from lms.certificate_generator import load_tuning, save_tuning, _DEFAULTS, list_templates, TUNING_PATH
        import json as _json

        courses = Course.query.order_by(Course.title).all()

        if request.method == 'POST':
            from lms.certificate_generator import invalidate_cache
            from lms.models import Certificate
            course_id = request.form.get('course_id', 'default')
            values = self._parse_tuning(request.form, _DEFAULTS)
            save_tuning(course_id, values)
            # Evict cached images so the new tuning takes effect immediately
            if course_id == 'default':
                certs = Certificate.query.with_entities(Certificate.id).all()
            else:
                certs = Certificate.query.with_entities(Certificate.id).filter_by(course_id=int(course_id)).all()
            for (cert_id,) in certs:
                invalidate_cache(cert_id)
            flash('Tuning saved.', 'success')
            return redirect(url_for('certificate_tuning.index'))

        try:
            with open(TUNING_PATH) as _f:
                raw_json = _json.load(_f)
        except (OSError, _json.JSONDecodeError):
            raw_json = {}

        course_tunings = {}
        for course in courses:
            course_tunings[course.id] = load_tuning(course.id)

        return self.render(
            'admin/certificate_tuning.html',
            courses=courses,
            course_tunings=course_tunings,
            raw_json=raw_json,
            defaults=load_tuning(),
            field_names=list(_DEFAULTS.keys()),
            preview_url=url_for('certificate_tuning.preview'),
            template_files=list_templates(),
        )


class UserPermissionsView(BaseView):
    """Manage per-admin permission restrictions. Accessible to full admins only."""

    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_full_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

    @expose('/')
    def index(self):
        admins = User.query.filter_by(is_admin=True).order_by(User.username).all()
        return self.render('admin/user_permissions.html',
                           admins=admins,
                           permissions=ADMIN_PERMISSIONS)

    @expose('/save/<int:user_id>', methods=['POST'])
    def save(self, user_id):
        user = User.query.get_or_404(user_id)
        if not user.is_admin:
            flash('Only admin users can have permission assignments.', 'warning')
            return redirect(url_for('user_permissions.index'))
        valid_keys = {p for p, _ in ADMIN_PERMISSIONS}
        selected = [p for p in request.form.getlist('permissions') if p in valid_keys]
        # If all permissions selected, treat as full admin (no restrictions)
        if len(selected) == len(ADMIN_PERMISSIONS):
            user.admin_permissions = None
        else:
            user.admin_permissions = selected if selected else []
        db.session.commit()
        status = 'full admin' if user.admin_permissions is None else f'{len(selected)} permissions'
        flash(f'{user.username} updated — {status}.', 'success')
        return redirect(url_for('user_permissions.index'))


def init_admin(app):
    """Initialize admin interface with all views"""
    admin = Admin(app, name='LMS Admin', index_view=AdminIndexView())
    admin.add_view(UserView(User, db.session))
    admin.add_view(CourseView(Course, db.session))
    admin.add_view(CourseManagementView(name='Course Management', endpoint='course_management'))
    admin.add_view(UserPermissionsView(name='Permissions', endpoint='user_permissions'))
    admin.add_view(ForumChannelView(ForumChannel, db.session))
    admin.add_view(ForumMessageView(ForumMessage, db.session))
    admin.add_view(ResourceView(Resource, db.session))
    admin.add_view(MoxoTestView(MoxoTest, db.session))
    admin.add_view(GoogleLoginView(name='Google Login', endpoint='google_login'))
    admin.add_view(CertificateTuningView(name='Certificate Tuning', endpoint='certificate_tuning'))
    admin.add_view(TranslateContentView(name='Translate', endpoint='translate'))
    admin.add_view(LogoutView(name='Logout', endpoint='logout'))
    return admin
