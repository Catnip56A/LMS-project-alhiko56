"""
Admin interface views and configuration
"""
import json
import os
import secrets
import requests
from datetime import datetime, timedelta
from flask import flash, redirect, url_for, request, current_app, session
from flask_admin import Admin, AdminIndexView, expose, BaseView
from flask_admin.contrib.sqla import ModelView
from flask_admin.form.upload import FileUploadField
from markupsafe import Markup
from wtforms import Form, FileField, StringField, TextAreaField, BooleanField
from wtforms.validators import DataRequired
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField
from wtforms.validators import Optional, DataRequired
import os
from yonca.google_drive_service import authenticate, upload_file, create_view_only_link, set_file_permissions
import secrets

def upload_gallery_image_to_drive(file, filename):
    """Upload a gallery image to Google Drive and return the public URL"""
    try:
        # Authenticate with Google Drive
        service = authenticate()
        if not service:
            print("Failed to authenticate with Google Drive for gallery upload")
            # Instead of returning None, raise an exception to be caught by the caller
            raise Exception("Google Drive authentication failed - user needs to link their Google account")

        # Create temporary directory if it doesn't exist
        temp_dir = os.path.join(current_app.static_folder, 'temp')
        os.makedirs(temp_dir, exist_ok=True)

        # Generate secure filename
        from werkzeug.utils import secure_filename
        import random
        secure_filename_str = secure_filename(filename)
        unique_filename = f"gallery_{random.randint(1000, 9999)}_{secure_filename_str}"
        temp_file_path = os.path.join(temp_dir, unique_filename)

        # Save file temporarily
        file.save(temp_file_path)

        try:
            # Upload to Google Drive
            drive_file_id = upload_file(service, temp_file_path, secure_filename_str)
            if not drive_file_id:
                print("Failed to upload gallery image to Google Drive")
                return None

            # Set file permissions to make it publicly accessible
            success = set_file_permissions(service, drive_file_id, make_public=True)
            print(f"DEBUG: set_file_permissions for gallery {drive_file_id} returned: {success}")
            if not success:
                print("Failed to set gallery image permissions")
                return None

            # Create view-only link (always treat gallery images as images)
            view_link = create_view_only_link(service, drive_file_id, is_image=True)
            if not view_link:
                print("Failed to create view link for gallery image")
                return None

            # Clean up temporary file
            try:
                os.remove(temp_file_path)
            except:
                pass

            return view_link

        except Exception as e:
            print(f"Error uploading gallery image to Drive: {e}")
            # Clean up temporary file on error
            try:
                os.remove(temp_file_path)
            except:
                pass
            return None

    except Exception as e:
        print(f"Error in gallery image upload: {e}")
        return None

def get_google_redirect_uri(redirect_uri=None):
    if redirect_uri:
        return redirect_uri
    uri = os.environ.get('GOOGLE_REDIRECT_URI')
    if not uri:
        raise RuntimeError("GOOGLE_REDIRECT_URI environment variable is not set")
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    return f"{parsed.scheme}://{parsed.netloc}/admin/google_login/"
from yonca.models import User, Course, ForumMessage, ForumChannel, TaviTest, Resource, db, HomeContent

class AdminIndexView(AdminIndexView):
    """Custom admin index view with authentication and home content management"""
    
    def render(self, template, **kwargs):
        """Override render to ensure admin_base_template is set"""
        if 'admin_base_template' not in kwargs:
            # Get base template from theme, with fallback
            try:
                base_template = self.admin.theme.base_template
            except AttributeError:
                # Fallback to default Flask-Admin base template
                base_template = 'admin/base.html'
            kwargs['admin_base_template'] = base_template
        return super().render(template, **kwargs)
    
    @expose('/', methods=['GET', 'POST'])
    def index(self):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('auth.login'))
        
        print(f"ADMIN ACCESS: {current_user.username} (ID: {current_user.id}) accessed home page editor")
        
        # Handle home content editing
        home_content = HomeContent.query.filter_by(is_active=True).first()
        print(f"DEBUG: Active home content query result: {home_content.id if home_content else 'None'}")
        if not home_content:
            home_content = HomeContent(
                welcome_title="Welcome to Yonca",
                subtitle="Your gateway to knowledge and community learning.",
                get_started_text="Get Started",
                logged_out_welcome_title="Welcome to Yonca",
                logged_out_subtitle="Join our learning community today!",
                logged_out_get_started_text="Sign Up Now",
                features=[
                    {"title": "Interactive Courses", "description": "Engage with dynamic course content and interactive quizzes."},
                    {"title": "Community Forum", "description": "Connect with fellow learners and share knowledge."},
                    {"title": "Resource Library", "description": "Access a comprehensive collection of learning materials."}
                ],
                logged_out_features=[
                    {"title": "Free Courses", "description": "Start learning with our free introductory courses."},
                    {"title": "Expert Instructors", "description": "Learn from industry professionals and educators."},
                    {"title": "Community Support", "description": "Get help and support from our active community."}
                ]
            )
            db.session.add(home_content)
            db.session.commit()
        
        form = HomeContentForm()
        
        if request.method == 'POST':
            print(f"DEBUG: POST request received at {request.url}")
            print(f"DEBUG: Form data keys: {list(request.form.keys())}")
            print(f"DEBUG: Raw form data: {dict(request.form)}")
            
            # Re-query for the active home content to ensure we have the current record
            home_content = HomeContent.query.filter_by(is_active=True).first()
            print(f"DEBUG: Re-queried active home_content ID: {home_content.id if home_content else 'None'}")
            
            if not home_content:
                print("DEBUG: No active home content found during POST, this should not happen")
                flash('Error: No active home content found.', 'error')
                return redirect(url_for('admin.index'))
            
            # Ensure the object is attached to the session
            db.session.add(home_content)
            
            form = HomeContentForm(request.form)
            print(f"DEBUG: Form validation: {form.validate()}")
            if not form.validate():
                print(f"DEBUG: Form errors: {form.errors}")
                print(f"DEBUG: Form data after validation attempt: {form.data}")
            
            # Validate basic form fields (relaxed validation)
            if form.validate():
                print(f"DEBUG: Form validation passed")
                print(f"DEBUG: Updating home_content record ID: {home_content.id}")

                # Log original values for comparison
                original_features_count = len(home_content.features) if home_content.features else 0
                original_logged_out_count = len(home_content.logged_out_features) if home_content.logged_out_features else 0
                
                # NOTE: Welcome title/subtitle/button fields removed from admin editor.
                # We intentionally do not update `welcome_title`, `subtitle`, `get_started_text`,
                # `logged_out_welcome_title`, `logged_out_subtitle`, or `logged_out_get_started_text` here.
                
                # Section content
                # Features title/subtitle (editable in admin)
                home_content.features_title = form.features_title.data
                home_content.features_subtitle = form.features_subtitle.data

                home_content.about_section_title = form.about_section_title.data
                home_content.about_section_description = form.about_section_description.data
                
                # Branding and navigation
                home_content.site_name = form.site_name.data
                
                # Handle logo upload
                logo_file = request.files.get('site_logo_file')
                logo_url = request.form.get('site_logo_url')
                
                print(f"DEBUG: logo_file = {logo_file}, filename = {logo_file.filename if logo_file else 'None'}")
                print(f"DEBUG: logo_url = {logo_url}")
                
                if logo_file and logo_file.filename:
                    # Upload logo to Google Drive
                    from werkzeug.utils import secure_filename
                    import os
                    import random
                    from yonca.google_drive_service import authenticate, upload_file, create_view_only_link
                    
                    # Create temporary directory for file processing
                    temp_dir = os.path.join(current_app.static_folder, 'temp')
                    os.makedirs(temp_dir, exist_ok=True)
                    print(f"DEBUG: temp_dir = {temp_dir}, exists = {os.path.exists(temp_dir)}")
                    
                    # Generate secure filename
                    filename = secure_filename(logo_file.filename)
                    unique_filename = f"logo_{random.randint(1000, 9999)}_{filename}"
                    temp_file_path = os.path.join(temp_dir, unique_filename)
                    print(f"DEBUG: temp_file_path = {temp_file_path}")
                    
                    # Save file temporarily
                    logo_file.save(temp_file_path)
                    print(f"DEBUG: file saved, exists = {os.path.exists(temp_file_path)}")
                    
                    # Upload to Google Drive
                    service = authenticate()
                    print(f"DEBUG: Google Drive service = {service}")
                    if service:
                        drive_file_id = upload_file(service, temp_file_path, filename)
                        print(f"DEBUG: drive_file_id = {drive_file_id}")
                        if drive_file_id:
                            view_link = create_view_only_link(service, drive_file_id, is_image=True)
                            print(f"DEBUG: view_link = {view_link}")
                            if view_link:
                                # Make the logo publicly viewable
                                success = set_file_permissions(service, drive_file_id, make_public=True)
                                print(f"DEBUG: set_file_permissions for logo {drive_file_id} returned: {success}")
                                
                                home_content.site_logo_url = view_link
                                print(f"DEBUG: Logo URL set to: {home_content.site_logo_url}")
                                flash('Logo uploaded successfully to Google Drive', 'success')
                            else:
                                flash('Failed to create view link for logo', 'error')
                        else:
                            flash('Failed to upload logo to Google Drive', 'error')
                    else:
                        flash('Failed to authenticate with Google Drive for logo upload', 'error')
                    
                    # Clean up temporary file
                    try:
                        os.remove(temp_file_path)
                    except:
                        pass
                elif logo_url:
                    # Use provided URL
                    home_content.site_logo_url = logo_url
                
                home_content.is_active = True  # Always keep home content active
                print(f"DEBUG: Setting is_active to: True (always active)")
                
                # Process features
                features = []
                logged_out_features = []
                
                # Get all form data
                form_data = request.form
                
                # Process logged in features
                feature_titles = [key for key in form_data.keys() if key.startswith('feature_title_')]
                for i in range(len(feature_titles)):
                    title_key = f'feature_title_{i}'
                    desc_key = f'feature_desc_{i}'
                    btn_text_key = f'feature_button_text_{i}'
                    btn_url_key = f'feature_button_url_{i}'
                    if title_key in form_data and desc_key in form_data:
                        title = form_data[title_key].strip()
                        desc = form_data[desc_key].strip()
                        btn_text = form_data.get(btn_text_key, '').strip()
                        btn_url = form_data.get(btn_url_key, '').strip()
                        if title or desc:  # Only add if there's content
                            item = {'title': title, 'description': desc}
                            if btn_text:
                                item['button_text'] = btn_text
                            if btn_url:
                                item['button_url'] = btn_url
                            features.append(item)
                
                # Process logged out features
                logged_out_titles = [key for key in form_data.keys() if key.startswith('logged_out_feature_title_')]
                for i in range(len(logged_out_titles)):
                    title_key = f'logged_out_feature_title_{i}'
                    desc_key = f'logged_out_feature_desc_{i}'
                    btn_text_key = f'logged_out_feature_button_text_{i}'
                    btn_url_key = f'logged_out_feature_button_url_{i}'
                    if title_key in form_data and desc_key in form_data:
                        title = form_data[title_key].strip()
                        desc = form_data[desc_key].strip()
                        btn_text = form_data.get(btn_text_key, '').strip()
                        btn_url = form_data.get(btn_url_key, '').strip()
                        if title or desc:  # Only add if there's content
                            item = {'title': title, 'description': desc}
                            if btn_text:
                                item['button_text'] = btn_text
                            if btn_url:
                                item['button_url'] = btn_url
                            logged_out_features.append(item)
                
                home_content.features = features
                home_content.logged_out_features = logged_out_features
                
                # Process What's New media
                # Use a dictionary to collect images by their index to maintain order
                gallery_images_dict = {}
                existing_images = home_content.gallery_images or []
                
                # Get all gallery indices from form data (alt, caption, and url fields)
                gallery_indices = set()
                for key in form_data.keys():
                    if key.startswith('gallery_alt_'):
                        index = key.replace('gallery_alt_', '')
                        gallery_indices.add(index)
                    elif key.startswith('gallery_caption_'):
                        index = key.replace('gallery_caption_', '')
                        gallery_indices.add(index)
                    elif key.startswith('gallery_url_'):
                        index = key.replace('gallery_url_', '')
                        gallery_indices.add(index)
                
                # Process each gallery index found in the form
                for index in sorted(gallery_indices, key=lambda x: int(x) if x.isdigit() else 0):
                    file_key = f'gallery_file_{index}'
                    url_key = f'gallery_url_{index}'
                    alt_key = f'gallery_alt_{index}'
                    caption_key = f'gallery_caption_{index}'
                    
                    alt = form_data.get(alt_key, '').strip()
                    caption = form_data.get(caption_key, '').strip()
                    
                    # Check if a URL was provided
                    url = form_data.get(url_key, '').strip()
                    if url:
                        # Handle direct URL (YouTube, Vimeo, direct video/image links)
                        gallery_images_dict[index] = {'url': url, 'alt': alt, 'caption': caption}
                        continue
                    
                    # Check if a file was uploaded for this index
                    if file_key in request.files and request.files[file_key].filename:
                        file = request.files[file_key]
                        if file and file.filename:
                            # Upload to Google Drive instead of local storage
                            try:
                                drive_url = upload_gallery_image_to_drive(file, file.filename)
                                if drive_url:
                                    # Add image with uploaded URL
                                    gallery_images_dict[index] = {'url': drive_url, 'alt': alt, 'caption': caption, 'drive_file_id': None}
                                else:
                                    flash(f'Failed to upload gallery image {file.filename} to Google Drive', 'error')
                            except Exception as e:
                                if "Google Drive authentication failed" in str(e):
                                    flash('Please link your Google account to upload images. Redirecting...', 'warning')
                                    return redirect(url_for('google_login.index'))
                                else:
                                    flash(f'Failed to upload gallery image {file.filename}: {str(e)}', 'error')
                    else:
                        # No new file uploaded - keep existing image but update alt/caption if provided
                        try:
                            index_num = int(index)
                            if index_num < len(existing_images):
                                # Get existing image and update only the alt/caption
                                existing_image = existing_images[index_num].copy()
                                if alt:
                                    existing_image['alt'] = alt
                                if caption:
                                    existing_image['caption'] = caption
                                gallery_images_dict[index] = existing_image
                        except (ValueError, IndexError):
                            pass  # Skip invalid indices
                
                # Convert dictionary to ordered list based on numeric indices
                gallery_images = []
                for idx in sorted(gallery_images_dict.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                    gallery_images.append(gallery_images_dict[idx])
                
                home_content.gallery_images = gallery_images
                
                print(f"DEBUG: About to commit changes to database")
                print(f"DEBUG: home_content.features: {home_content.features}")
                print(f"DEBUG: home_content.logged_out_features: {home_content.logged_out_features}")
                print(f"DEBUG: home_content.gallery_images: {home_content.gallery_images}")
                print(f"DEBUG: home_content.site_logo_url: {home_content.site_logo_url}")
                
                db.session.commit()
                print(f"DEBUG: Database commit successful")
                
                # Verify the data was actually saved
                db.session.refresh(home_content)
                print(f"DEBUG: After commit - record ID: {home_content.id}")
                print(f"DEBUG: After commit - welcome_title: {home_content.welcome_title}")
                print(f"DEBUG: After commit - features: {home_content.features}")
                print(f"DEBUG: After commit - site_logo_url: {home_content.site_logo_url}")
                print(f"DEBUG: After commit - logged_out_features: {home_content.logged_out_features}")
                
                print(f"ADMIN ACTION: Home content updated by {current_user.username} (ID: {current_user.id})")
                print(f"  - Features: {original_features_count} → {len(features)} items")
                print(f"  - Logged-out features: {original_logged_out_count} → {len(logged_out_features)} items")
                flash('Home content updated successfully!', 'success')
                return redirect(url_for('admin.index'))
            else:
                print(f"DEBUG: Form validation failed")
                flash('Please fill in all required fields.', 'error')
        
        # Pre-populate form (welcome fields omitted)
        
        # Section content
        form.features_title.data = getattr(home_content, 'features_title', None)
        form.features_subtitle.data = getattr(home_content, 'features_subtitle', None)

        form.about_section_title.data = home_content.about_section_title
        form.about_section_description.data = home_content.about_section_description
        
        # Branding and navigation
        form.site_name.data = home_content.site_name
        form.site_logo_url.data = home_content.site_logo_url
        
        form.is_active.data = home_content.is_active
        
        return self.render('admin/index.html', form=form, home_content=home_content)

class SecureModelView(ModelView):
    """Base model view with authentication"""
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
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
        return current_user.is_authenticated and current_user.is_admin
    
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
            from yonca.google_drive_service import authenticate
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
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('auth.login'))
        
        # Fetch all courses
        courses = Course.query.all()
        return self.render('admin/course_management.html', courses=courses)
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

class HomeContentForm(FlaskForm):
    """Form for editing home content"""
    # Section content
    features_title = StringField('Features Title', [Optional()], default="Our Features")
    features_subtitle = TextAreaField('Features Subtitle', [Optional()], default="Discover what makes our platform special.")

    about_section_title = StringField('About Section Title', [Optional()], default="About Yonca")
    about_section_description = TextAreaField('About Section Description', [Optional()], default="Learn about our mission and vision.")
    
    # Branding and navigation
    site_name = StringField('Site Name', [Optional()], default="Yonca")
    site_logo_url = StringField('Logo URL', [Optional()])
    site_logo_file = FileField('Logo File', [Optional()])
    
    is_active = BooleanField('Active', default=True)

class UserView(SecureModelView):
    """Admin view for User model with password management"""
    column_list = ('id', 'username', 'email', 'is_admin', 'courses')
    column_searchable_list = ['username', 'email']
    form_columns = ('username', 'email', 'is_admin', 'is_teacher', 'courses', 'new_password')
    form_excluded_columns = ('_password', 'password')
    column_formatters = {
        'courses': lambda v, c, m, p: ', '.join([course.title for course in m.courses]) if m.courses else 'None'
    }
    
    form_extra_fields = {
        'new_password': StringField('New Password', [Optional()], description='Leave blank to keep current password')
    }
    
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
    profile_emoji = StringField('Profile Emoji', [Optional()])

class CourseView(SecureModelView):
    """Admin view for Course model with custom dropdown menu management"""
    column_list = ('id', 'title', 'description', 'time_slot', 'profile_emoji', 'users')
    column_searchable_list = ['title', 'description']
    form = CourseForm
    form_excluded_columns = ('dropdown_menu',)
    column_formatters = {
        'users': lambda v, c, m, p: ', '.join([user.username for user in m.users]) if m.users else 'None'
    }

    @expose('/edit/', methods=['GET', 'POST'])
    def edit_view(self, id=None, url=None):
        """Custom edit view with dropdown menu management"""
        if not current_user.is_authenticated or not current_user.is_admin:
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
            course.profile_emoji = request.form.get('profile_emoji', '')
            
            # Parse tags from comma-separated input
            tags_input = request.form.get('tags', '').strip()
            course.tags = [tag.strip() for tag in tags_input.split(',') if tag.strip()] if tags_input else []

            # Course page content
            course.page_welcome_title = request.form.get('page_welcome_title', '')
            course.page_subtitle = request.form.get('page_subtitle', '')
            course.page_description = request.form.get('page_description', '')
            course.page_show_navigation = 'page_show_navigation' in request.form
            course.page_show_footer = 'page_show_footer' in request.form
            course.page_show_title = 'page_show_title' in request.form
            course.page_show_description = 'page_show_description' in request.form
            
            # Course tab labels
            course.tab_content_label = request.form.get('tab_content_label', 'Content')
            course.tab_assignments_label = request.form.get('tab_assignments_label', 'Assignments')
            course.tab_announcements_label = request.form.get('tab_announcements_label', 'Announcements')
            course.tab_reviews_label = request.form.get('tab_reviews_label', 'Reviews')

            # Handle course page features
            features = []
            feature_count = 0

            while f'feature_title_{feature_count}' in request.form:
                title = request.form.get(f'feature_title_{feature_count}', '').strip()
                desc = request.form.get(f'feature_desc_{feature_count}', '').strip()
                image = request.form.get(f'feature_image_{feature_count}', '').strip()

                if title or desc or image:  # Only add if there's content
                    features.append({
                        'title': title,
                        'description': desc,
                        'image': image
                    })

                feature_count += 1

            course.page_features = features

            db.session.commit()
            
            # Automatically translate the course content
            try:
                from yonca.content_translator import auto_translate_course
                auto_translate_course(course)
                db.session.commit()
                print(f"Auto-translated course: {course.title}")
            except Exception as e:
                print(f"Warning: Failed to auto-translate course {course.id}: {str(e)}")
            
            flash('Course updated successfully!', 'success')
            return redirect(url_for('admin.index'))

        # Get existing menu items (no longer used, but keep for backward compatibility)
        menu_items = course.dropdown_menu or []

        # For editing, we need to show the original English text, not translated versions
        # Create a dict with English versions of translatable fields
        from yonca.content_translator import get_translated_content
        english_course_data = {
            'id': course.id,
            'title': get_translated_content('course', course.id, 'title', course.title, 'en') or course.title,
            'description': get_translated_content('course', course.id, 'description', course.description, 'en') or course.description,
            'time_slot': course.time_slot,
            'profile_emoji': course.profile_emoji,
            'page_welcome_title': get_translated_content('course', course.id, 'page_welcome_title', course.page_welcome_title or '', 'en') or course.page_welcome_title,
            'page_subtitle': get_translated_content('course', course.id, 'page_subtitle', course.page_subtitle or '', 'en') or course.page_subtitle,
            'page_description': get_translated_content('course', course.id, 'page_description', course.page_description or '', 'en') or course.page_description,
            'page_show_navigation': course.page_show_navigation,
            'page_show_footer': course.page_show_footer,
            'page_show_title': course.page_show_title,
            'page_show_description': course.page_show_description,
            'page_features': course.page_features,
            'dropdown_menu': course.dropdown_menu
        }

        return self.render('admin/course_edit.html',
                         course=english_course_data,
                         menu_items=menu_items,
                         menu_item_count=len(menu_items))

    @expose('/new/', methods=['GET', 'POST'])
    def create_view(self):
        """Custom create view with dropdown menu management"""
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('auth.login'))

        if request.method == 'POST':
            # Parse tags from comma-separated input
            tags_input = request.form.get('tags', '').strip()
            tags = [tag.strip() for tag in tags_input.split(',') if tag.strip()] if tags_input else []
            
            course = Course(
                title=request.form.get('title', ''),
                description=request.form.get('description', ''),
                time_slot=request.form.get('time_slot', ''),
                profile_emoji=request.form.get('profile_emoji', ''),
                tags=tags,
                page_welcome_title=request.form.get('page_welcome_title', ''),
                page_subtitle=request.form.get('page_subtitle', ''),
                page_description=request.form.get('page_description', ''),
                page_show_navigation='page_show_navigation' in request.form,
                page_show_footer='page_show_footer' in request.form,
                page_show_title='page_show_title' in request.form,
                page_show_description='page_show_description' in request.form
            )

            # Handle course page features
            features = []
            feature_count = 0

            while f'feature_title_{feature_count}' in request.form:
                title = request.form.get(f'feature_title_{feature_count}', '').strip()
                desc = request.form.get(f'feature_desc_{feature_count}', '').strip()
                image = request.form.get(f'feature_image_{feature_count}', '').strip()

                if title or desc or image:  # Only add if there's content
                    features.append({
                        'title': title,
                        'description': desc,
                        'image': image
                    })

                feature_count += 1

            course.page_features = features

            db.session.add(course)
            db.session.commit()
            
            # Automatically translate the new course content
            try:
                from yonca.content_translator import auto_translate_course
                auto_translate_course(course)
                db.session.commit()
                print(f"Auto-translated new course: {course.title}")
            except Exception as e:
                print(f"Warning: Failed to auto-translate new course {course.id}: {str(e)}")
            
            flash('Course created successfully!', 'success')
            return redirect(url_for('admin.index'))

        return self.render('admin/course_edit.html',
                         course=None,
                         menu_items=[],
                         menu_item_count=0)

    @expose('/page_builder/', methods=['GET', 'POST'])
    def page_builder(self):
        """Page builder for course descriptions"""
        print("DEBUG PAGE_BUILDER: Route called")  # ADDED
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('auth.login'))

        course_id = request.args.get('course_id') or request.form.get('course_id')
        print(f"DEBUG PAGE_BUILDER: course_id = {course_id}, request.method = {request.method}")  # ADDED
        if not course_id:
            flash('Course ID is required', 'error')
            return redirect(url_for('admin.index'))

        course = self.get_one(course_id)
        if not course:
            flash('Course not found', 'error')
            return redirect(url_for('admin.index'))

        if request.method == 'POST':
            # Handle page builder save
            print("DEBUG PAGE_BUILDER: Handling POST request")  # ADDED
            try:
                import json
                from yonca.content_translator import auto_translate_page_builder
                page_builder_data = request.form.get('page_builder_data', '[]')
                print(f"DEBUG PAGE_BUILDER: Received page_builder_data: {page_builder_data[:100]}...")  # Debug log
                
                # Validate JSON
                parsed_data = json.loads(page_builder_data)
                print(f"DEBUG: Parsed JSON successfully, blocks count: {len(parsed_data)}")  # Debug log
                print(f"DEBUG: Course ID: {course.id}, Current page_builder_data: {course.page_builder_data}")  # Debug
                
                # Update the course
                course.page_builder_data = parsed_data
                print(f"DEBUG: Updated course.page_builder_data to: {course.page_builder_data}")  # Debug
                
                # Make sure the session recognizes the change
                db.session.add(course)
                db.session.commit()
                print(f"DEBUG: Committed to database")  # Debug log
                
                # Verify the save
                db.session.refresh(course)
                print(f"DEBUG: Refreshed course, page_builder_data now: {course.page_builder_data}")  # Debug
                print(f"DEBUG: Type of page_builder_data: {type(course.page_builder_data)}")  # Debug type
                print(f"DEBUG: Length of page_builder_data: {len(course.page_builder_data) if course.page_builder_data else 0}")  # Debug length
                
                # Auto-translate page builder content
                print("DEBUG: Starting auto-translation for page builder content...")
                auto_translate_page_builder(course, db.session)
                db.session.commit()
                print("DEBUG: Auto-translation complete and committed")
                
                flash('Page builder content saved and translated successfully!', 'success')
                # Redirect back to page builder by refreshing the current page
                return redirect(f'/admin/course/page_builder/?course_id={course_id}')
                
            except json.JSONDecodeError as e:
                error_msg = f'Invalid JSON: {str(e)}'
                print(f"DEBUG: JSON Error: {error_msg}")  # Debug log
                flash(error_msg, 'error')
                return redirect(f'/admin/course/page_builder/?course_id={course_id}')
            except Exception as e:
                import traceback
                error_msg = f'Error saving page builder: {str(e)}'
                print(f"DEBUG: Exception: {error_msg}")  # Debug log
                print(f"DEBUG: Traceback: {traceback.format_exc()}")  # Full traceback
                flash(error_msg, 'error')
                return redirect(f'/admin/course/page_builder/?course_id={course_id}')

        # Log what we're passing to the template
        print(f"DEBUG PAGE_BUILDER: Rendering template with course.page_builder_data = {course.page_builder_data}")  # Debug
        print(f"DEBUG PAGE_BUILDER: Type: {type(course.page_builder_data)}, Length: {len(course.page_builder_data) if course.page_builder_data else 0}")  # Debug
        
        return self.render('admin/page_builder.html',
                         course=course,
                         page_builder_data=course.page_builder_data or [])

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
                from yonca.google_drive_service import authenticate, upload_file, create_view_only_link
                
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
                from yonca.google_drive_service import authenticate, upload_file, create_view_only_link
                
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

class TaviTestView(SecureModelView):
    """Admin view for TaviTest model"""
    column_list = ('id', 'user_id', 'result', 'timestamp')
    column_searchable_list = ['result']
    form_excluded_columns = ('timestamp',)

class ForumChannelView(SecureModelView):
    """Admin view for ForumChannel model"""
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

class AboutCompanyView(BaseView):
    """About Company configuration view"""
    
    @expose('/', methods=['GET', 'POST'])
    def index(self):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('auth.login'))
        
        # Handle about company content editing
        home_content = HomeContent.query.filter_by(is_active=True).first()
        if not home_content:
            home_content = HomeContent(
                about_welcome_title="Welcome to Yonca",
                about_subtitle="Join our learning community and discover amazing features designed to enhance your educational experience.",
                about_features=[{"title": "Interactive Courses", "description": "Engage with dynamic course content and interactive learning materials."}, {"title": "Study Groups", "description": "Collaborate with fellow learners in our vibrant study communities."}, {"title": "Expert Support", "description": "Get help from our team of educational experts and specialists."}]
            )
            db.session.add(home_content)
            db.session.commit()
        
        form = AboutCompanyForm()
        
        if request.method == 'POST' and form.validate_on_submit():
            try:
                # About page content
                home_content.about_welcome_title = form.about_welcome_title.data
                home_content.about_subtitle = form.about_subtitle.data
                
                # About features section
                home_content.about_features_title = form.about_features_title.data
                home_content.about_features_subtitle = form.about_features_subtitle.data
                
                # About gallery section
                home_content.about_gallery_title = form.about_gallery_title.data
                home_content.about_gallery_subtitle = form.about_gallery_subtitle.data
                
                # Process about features dynamically
                about_features = []
                form_data = request.form
                
                # Process about features
                about_feature_titles = [key for key in form_data.keys() if key.startswith('about_feature_title_')]
                for i in range(len(about_feature_titles)):
                    title_key = f'about_feature_title_{i}'
                    desc_key = f'about_feature_desc_{i}'
                    if title_key in form_data and desc_key in form_data:
                        title = form_data[title_key].strip()
                        desc = form_data[desc_key].strip()
                        if title or desc:  # Only add if there's content
                            about_features.append({'title': title, 'description': desc})
                
                home_content.about_features = about_features
                
                # Process About Company gallery
                # Use a dictionary to collect images by their index to maintain order
                about_gallery_images_dict = {}
                existing_about_images = home_content.about_gallery_images or []
                
                # Get all gallery indices from form data (alt, caption, and url fields)
                gallery_indices = set()
                for key in form_data.keys():
                    if key.startswith('about_gallery_alt_'):
                        index = key.replace('about_gallery_alt_', '')
                        gallery_indices.add(index)
                    elif key.startswith('about_gallery_caption_'):
                        index = key.replace('about_gallery_caption_', '')
                        gallery_indices.add(index)
                    elif key.startswith('about_gallery_url_'):
                        index = key.replace('about_gallery_url_', '')
                        gallery_indices.add(index)
                
                # Process each gallery index found in the form
                for index in sorted(gallery_indices, key=lambda x: int(x) if x.isdigit() else 0):
                    file_key = f'about_gallery_file_{index}'
                    url_key = f'about_gallery_url_{index}'
                    alt_key = f'about_gallery_alt_{index}'
                    caption_key = f'about_gallery_caption_{index}'
                    
                    alt = form_data.get(alt_key, '').strip()
                    caption = form_data.get(caption_key, '').strip()
                    
                    # Check if a URL was provided
                    url = form_data.get(url_key, '').strip()
                    if url:
                        # Handle direct URL (YouTube, Vimeo, direct video/image links)
                        about_gallery_images_dict[index] = {'url': url, 'alt': alt, 'caption': caption}
                        continue
                    
                    # Check if a file was uploaded for this index
                    if file_key in request.files and request.files[file_key].filename:
                        file = request.files[file_key]
                        if file and file.filename:
                            # Upload to Google Drive instead of local storage
                            drive_url = upload_gallery_image_to_drive(file, file.filename)
                            if drive_url:
                                # Add image with uploaded URL
                                about_gallery_images_dict[index] = {'url': drive_url, 'alt': alt, 'caption': caption, 'drive_file_id': None}
                            else:
                                flash(f'Failed to upload about gallery image {file.filename} to Google Drive', 'error')
                    else:
                        # No new file uploaded - keep existing image but update alt/caption if provided
                        try:
                            index_num = int(index)
                            if index_num < len(existing_about_images):
                                # Get existing image and update only the alt/caption
                                existing_image = existing_about_images[index_num].copy()
                                if alt:
                                    existing_image['alt'] = alt
                                if caption:
                                    existing_image['caption'] = caption
                                about_gallery_images_dict[index] = existing_image
                        except (ValueError, IndexError):
                            pass  # Skip invalid indices
                
                # Convert dictionary to ordered list based on numeric indices
                about_gallery_images = []
                for idx in sorted(about_gallery_images_dict.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                    about_gallery_images.append(about_gallery_images_dict[idx])
                
                home_content.about_gallery_images = about_gallery_images
                
                db.session.commit()
                flash('About Company content updated successfully!', 'success')
                return redirect(url_for('about_company.index'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating content: {str(e)}', 'error')
        
        # Populate form with existing data
        form.about_welcome_title.data = home_content.about_welcome_title
        form.about_subtitle.data = home_content.about_subtitle
        form.about_features_title.data = home_content.about_features_title
        form.about_features_subtitle.data = home_content.about_features_subtitle
        form.about_gallery_title.data = home_content.about_gallery_title
        form.about_gallery_subtitle.data = home_content.about_gallery_subtitle
        
        return self.render('admin/about_company.html', form=form, home_content=home_content)

class AboutCompanyForm(FlaskForm):
    """Form for About Company configuration"""
    
    # About page content
    about_welcome_title = StringField('About Page Welcome Title', [Optional()], default="Welcome to Yonca")
    about_subtitle = TextAreaField('About Page Subtitle', [Optional()], default="Join our learning community and discover amazing features designed to enhance your educational experience.")
    
    # About features section
    about_features_title = StringField('About Features Title', [Optional()], default="Our Features")
    about_features_subtitle = TextAreaField('About Features Subtitle', [Optional()], default="Discover what makes our platform special.")
    
    # About gallery section
    about_gallery_title = StringField('About Gallery Title', [Optional()], default="What's New")
    about_gallery_subtitle = TextAreaField('About Gallery Subtitle', [Optional()], default="Discover the latest updates, new features, and exciting developments in our learning platform.")

class TranslateContentView(BaseView):
    """View for translating all content with one click"""
    
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
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
        from yonca.job_manager import job_manager

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
        from yonca.job_manager import job_manager

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
        """Delete all translations for Azerbaijani and Russian"""
        from flask import jsonify
        
        if not self.is_accessible():
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        try:
            from yonca.models import ContentTranslation, Translation
            
            # Count translations before deletion
            az_content_count = ContentTranslation.query.filter_by(target_language='az').count()
            ru_content_count = ContentTranslation.query.filter_by(target_language='ru').count()
            az_cache_count = Translation.query.filter_by(target_language='az').count()
            ru_cache_count = Translation.query.filter_by(target_language='ru').count()
            
            total_before = az_content_count + ru_content_count + az_cache_count + ru_cache_count
            
            # Delete from ContentTranslation table
            ContentTranslation.query.filter(ContentTranslation.target_language.in_(['az', 'ru'])).delete()
            
            # Delete from Translation cache table
            Translation.query.filter(Translation.target_language.in_(['az', 'ru'])).delete()
            
            db.session.commit()
            
            message = f"Deleted {total_before} total translations ({az_content_count + az_cache_count} Azerbaijani, {ru_content_count + ru_cache_count} Russian)."
            
            return jsonify({'success': True, 'message': message, 'stats': {
                'az_content_translations': az_content_count,
                'ru_content_translations': ru_content_count,
                'az_cache_translations': az_cache_count,
                'ru_cache_translations': ru_cache_count,
                'total_deleted': total_before
            }})
            
        except Exception as e:
            from flask import jsonify
            import traceback
            error_details = traceback.format_exc()
            print(f"Delete translations error: {error_details}")
            return jsonify({'success': False, 'error': str(e)}), 500

def init_admin(app):
    """Initialize admin interface with all views"""
    admin = Admin(app, name='Yonca Admin', index_view=AdminIndexView())
    admin.add_view(UserView(User, db.session))
    admin.add_view(CourseView(Course, db.session))
    admin.add_view(CourseManagementView(name='Course Management', endpoint='course_management'))
    admin.add_view(ForumChannelView(ForumChannel, db.session))
    admin.add_view(SecureModelView(ForumMessage, db.session))
    admin.add_view(ResourceView(Resource, db.session))
    admin.add_view(TaviTestView(TaviTest, db.session))
    admin.add_view(AboutCompanyView(name='About Company', endpoint='about_company'))
    admin.add_view(GoogleLoginView(name='Google Login', endpoint='google_login'))
    admin.add_view(TranslateContentView(name='Translate', endpoint='translate'))
    admin.add_view(LogoutView(name='Logout', endpoint='logout'))
    return admin
