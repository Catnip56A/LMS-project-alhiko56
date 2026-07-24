
from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify, current_app, abort
from markupsafe import Markup
from flask_babel import get_locale, _
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from lms.upload_validation import validate_upload, UploadValidationError
import os
from datetime import datetime as dt

main_bp = Blueprint('main', __name__)

def _folder_is_ancestor_of(folder_id, target_id):
    """Return True if folder_id is an ancestor (parent/grandparent/…) of target_id."""
    from lms.models import CourseContentFolder
    cur = CourseContentFolder.query.get(target_id)
    while cur and cur.parent_folder_id is not None:
        if cur.parent_folder_id == folder_id:
            return True
        cur = CourseContentFolder.query.get(cur.parent_folder_id)
    return False


@main_bp.route('/', methods=['GET', 'POST'])
def index():
    """Serve main index page"""
    from lms.models import SiteSettings, Resource, PDFDocument, db

    # Handle POST requests for deletions and actions
    if request.method == 'POST':
        action = request.form.get('action')

        # Reorder root folders
        if action == 'reorder_root_folders' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContentFolder
            folder_order = request.form.get('folder_order', '')
            course_id_raw = request.form.get('course_id')
            try:
                course_id_int = int(course_id_raw) if course_id_raw and str(course_id_raw).isdigit() else None
            except Exception:
                course_id_int = None

            if folder_order:
                folder_ids = [int(fid) for fid in folder_order.split(',') if fid.isdigit()]
                for idx, folder_id in enumerate(folder_ids):
                    folder = CourseContentFolder.query.get(folder_id)
                    # Only update root-level folders that belong to the specified course
                    if folder and folder.parent_folder_id is None and (course_id_int is None or folder.course_id == course_id_int):
                        folder.order = idx + 1
                db.session.commit()
                flash('Root folder order updated!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course_id_int or 0))

        # Delete resource
        if action == 'delete_resource' and current_user.is_authenticated:
            from lms.google_drive_service import authenticate, delete_file
            resource_id = request.form.get('resource_id')
            resource = Resource.query.get(resource_id)
            if not resource:
                flash('Resource not found.', 'error')
                return redirect(url_for('main.index'))
            # Check permission: must be the uploader or an admin
            if resource.uploaded_by != current_user.id and not current_user.is_admin:
                flash('You do not have permission to delete this resource.', 'error')
                return redirect(url_for('main.index'))
            # Delete from Google Drive only if the app uploaded it (not imported from user's Drive)
            if resource.drive_file_id and not resource.is_imported:
                service = authenticate()
                if service:
                    try:
                        delete_file(service, resource.drive_file_id)
                    except Exception as e:
                        current_app.logger.error(f"Error deleting resource from Google Drive: {e}")
            # Delete from database
            db.session.delete(resource)
            db.session.commit()
            flash('Resource deleted successfully!', 'success')
            return redirect(url_for('main.index'))

        # Delete PDF
        if action == 'delete_pdf' and current_user.is_authenticated:
            from lms.google_drive_service import authenticate, delete_file
            pdf_id = request.form.get('pdf_id')
            pdf = PDFDocument.query.get(pdf_id)
            if not pdf:
                flash('PDF not found.', 'error')
                return redirect(url_for('main.index'))
            # Check permission: must be the uploader or an admin
            if pdf.uploaded_by != current_user.id and not current_user.is_admin:
                flash('You do not have permission to delete this PDF.', 'error')
                return redirect(url_for('main.index'))
            # Delete from Google Drive only if the app uploaded it (not imported from user's Drive)
            if pdf.drive_file_id and not pdf.is_imported:
                service = authenticate()
                if service:
                    try:
                        delete_file(service, pdf.drive_file_id)
                    except Exception as e:
                        current_app.logger.error(f"Error deleting PDF from Google Drive: {e}")
            # Delete from database
            db.session.delete(pdf)
            db.session.commit()
            flash('PDF deleted successfully!', 'success')
            return redirect(url_for('main.index'))

    # Always return a response, even if database is unavailable
    try:
        site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    except Exception as e:
        # Log the error but don't crash - return empty SiteSettings
        current_app.logger.error(f"Database error in index route: {e}")
        site_settings = SiteSettings()

    return render_template('index.html', is_authenticated=current_user.is_authenticated, site_settings=site_settings)


@main_bp.route('/course/<int:course_id>/join', methods=['POST'])
@login_required
def join_public_course(course_id):
    """Instant-join path: only for courses explicitly marked open-source/public."""
    from lms.models import Course, Enrollment, JOIN_VIA_INSTANT_PUBLIC, db

    course = Course.query.get_or_404(course_id)
    if not course.is_public:
        flash(_('This course is not open for instant joining.'), 'error')
        return redirect(url_for('main.course_page_enrolled', course_id=course.id))

    if current_user not in course.users:
        db.session.add(Enrollment(user=current_user, course=course, joined_via=JOIN_VIA_INSTANT_PUBLIC))
        db.session.commit()
        flash(_('You have joined %(title)s.', title=course.title), 'success')
    return redirect(url_for('main.course_page_enrolled', course_id=course.id))


def _redeem_promo_code(code_str, joined_via):
    """Validate and redeem a promo code for current_user.

    Returns (course, error_message) — exactly one of which is None/falsy.
    """
    from lms.models import PromoCode, Enrollment, db

    code_str = (code_str or '').strip()
    if not code_str:
        return None, _('Please enter a promo code.')

    promo = PromoCode.query.filter_by(code=code_str).first()
    if not promo:
        return None, _('Invalid promo code.')
    if not promo.is_valid:
        return None, _('This promo code has expired or reached its use limit.')

    course = promo.course
    if current_user in course.users:
        return course, None  # already enrolled — redemption is a no-op success

    db.session.add(Enrollment(user=current_user, course=course, joined_via=joined_via, promo_code=promo))
    promo.uses_count += 1
    db.session.commit()
    return course, None


@main_bp.route('/join', methods=['GET', 'POST'])
@login_required
def join_with_code():
    """Promo-code join path: type a code."""
    from lms.models import JOIN_VIA_PROMO_CODE

    if request.method == 'POST':
        course, error = _redeem_promo_code(request.form.get('code'), JOIN_VIA_PROMO_CODE)
        if error:
            flash(error, 'error')
            return render_template('join.html')
        flash(_('You have joined %(title)s.', title=course.title), 'success')
        return redirect(url_for('main.course_page_enrolled', course_id=course.id))
    return render_template('join.html')


@main_bp.route('/join/<code>', methods=['GET', 'POST'])
def join_via_link(code):
    """Direct-link join path: a shareable URL wrapping a promo code."""
    from lms.models import PromoCode, JOIN_VIA_DIRECT_LINK

    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=url_for('main.join_via_link', code=code)))

    promo = PromoCode.query.filter_by(code=code).first()
    if not promo:
        abort(404)

    if request.method == 'POST':
        course, error = _redeem_promo_code(code, JOIN_VIA_DIRECT_LINK)
        if error:
            flash(error, 'error')
            return redirect(url_for('main.index'))
        flash(_('You have joined %(title)s.', title=course.title), 'success')
        return redirect(url_for('main.course_page_enrolled', course_id=course.id))

    # GET is a confirmation page only — no state change, so link prefetch/scanners can't auto-join someone
    already_enrolled = current_user in promo.course.users
    return render_template('join_confirm.html', promo=promo, already_enrolled=already_enrolled)


@main_bp.route('/course/<int:course_id>/quiz/<int:quiz_id>', methods=['GET', 'POST'])
@login_required
def quiz_overview(course_id, quiz_id):
    from lms.models import Course, Quiz, QuizAttempt, SiteSettings, db

    course = Course.query.get_or_404(course_id)
    quiz = Quiz.query.filter_by(id=quiz_id, course_id=course_id).first_or_404()
    is_staff = current_user.is_teacher or current_user.is_admin
    if not is_staff and current_user not in course.users:
        flash(_('You must be enrolled in this course to take this quiz.'), 'error')
        return redirect(url_for('main.course_page_enrolled', course_id=course_id))

    attempts = (QuizAttempt.query
                .filter_by(quiz_id=quiz.id, user_id=current_user.id)
                .order_by(QuizAttempt.started_at.desc())
                .all())
    attempts_used = len(attempts)
    can_start = quiz.max_attempts is None or attempts_used < quiz.max_attempts

    if request.method == 'POST':
        if not can_start:
            flash(_('You have used all your attempts for this quiz.'), 'error')
            return redirect(url_for('main.quiz_overview', course_id=course_id, quiz_id=quiz_id))
        attempt = QuizAttempt(quiz=quiz, user=current_user)
        db.session.add(attempt)
        db.session.commit()
        return redirect(url_for('main.quiz_attempt', attempt_id=attempt.id))

    site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    return render_template('quiz_overview.html', course=course, quiz=quiz,
                            attempts=attempts, attempts_used=attempts_used, can_start=can_start,
                            site_settings=site_settings, current_locale=str(get_locale()))


@main_bp.route('/quiz/attempt/<int:attempt_id>', methods=['GET', 'POST'])
@login_required
def quiz_attempt(attempt_id):
    from lms.models import QuizAttempt, QuizAnswer, SiteSettings, db

    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        abort(403)

    if attempt.submitted_at:
        return redirect(url_for('main.quiz_result', attempt_id=attempt.id))

    quiz = attempt.quiz
    if request.method == 'POST':
        # Deliberately doesn't reject a slightly-late POST here — the countdown timer
        # (rendered client-side) auto-submits at the deadline, so server-side rejection
        # would just punish normal network latency for an honest on-time submission.
        for question in quiz.questions:
            field_name = f'question_{question.id}'
            if question.question_type == 'mcq':
                raw = request.form.get(field_name)
                try:
                    value = int(raw) if raw not in (None, '') else None
                except (TypeError, ValueError):
                    # Malformed submission — grade as unanswered rather than 500ing
                    value = None
            elif question.question_type == 'true_false':
                raw = request.form.get(field_name)
                value = {'true': True, 'false': False}.get(raw)
            else:
                value = request.form.get(field_name, '')
            db.session.add(QuizAnswer(attempt=attempt, question_id=question.id, answer=value))
        attempt.grade()
        db.session.commit()
        return redirect(url_for('main.quiz_result', attempt_id=attempt.id))

    site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    return render_template('quiz_take.html', attempt=attempt, quiz=quiz,
                            site_settings=site_settings, current_locale=str(get_locale()))


@main_bp.route('/quiz/attempt/<int:attempt_id>/result')
@login_required
def quiz_result(attempt_id):
    from lms.models import QuizAttempt, SiteSettings

    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        abort(403)
    if not attempt.submitted_at:
        return redirect(url_for('main.quiz_attempt', attempt_id=attempt.id))

    site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    return render_template('quiz_result.html', attempt=attempt, quiz=attempt.quiz,
                            site_settings=site_settings, current_locale=str(get_locale()))


# Enrolled-only course page
@main_bp.route('/course/<int:course_id>', methods=['GET', 'POST'])
def course_page_enrolled(course_id):
    from lms.models import Course, SiteSettings, CourseContent, CourseAssignment, CourseAnnouncement, CourseContentFolder, CourseAssignmentSubmission, CourseAnnouncementReply, CourseReview, db
    from datetime import datetime

    # Find course by id
    course = Course.query.get(course_id)
    if not course:
        abort(404)



    # Check enrollment status
    enrolled = current_user.is_authenticated and (current_user in course.users or current_user.is_teacher or current_user.is_admin)

    # Handle POST requests only if enrolled
    if request.method == 'POST':
        if not enrolled:
            flash('You must be enrolled in this course to perform this action.', 'error')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        action = request.form.get('action')
        
        # Add announcement
        if action == 'add_announcement' and (current_user.is_teacher or current_user.is_admin):
            title = request.form.get('announcement_title')
            message = request.form.get('announcement_message')
            is_published = request.form.get('announcement_published') == 'on'
            
            new_announcement = CourseAnnouncement(
                course_id=course.id,
                title=title,
                message=message,
                is_published=is_published,
                created_at=datetime.now()
            )
            db.session.add(new_announcement)
            db.session.commit()
            flash('Announcement added successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Add assignment
        elif action == 'add_assignment' and (current_user.is_teacher or current_user.is_admin):
            title = request.form.get('assignment_title')
            description = request.form.get('assignment_description')
            due_date_str = request.form.get('assignment_due_date')
            points = request.form.get('assignment_points', 100)
            is_published = request.form.get('assignment_published') == 'on'
            
            due_date = None
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    pass
            
            new_assignment = CourseAssignment(
                course_id=course.id,
                title=title,
                description=description,
                due_date=due_date,
                points=int(points),
                is_published=is_published,
                created_at=datetime.now()
            )
            db.session.add(new_assignment)
            db.session.commit()
            flash('Assignment created successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Edit assignment
        elif action == 'edit_assignment' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseAssignment
            assignment_id = request.form.get('assignment_id')
            if not assignment_id:
                flash('Invalid assignment ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            try:
                assignment_id = int(assignment_id)
            except (ValueError, TypeError):
                flash('Invalid assignment ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))

            assignment = CourseAssignment.query.get(assignment_id)
            
            if not assignment or assignment.course_id != course.id:
                flash('Assignment not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            assignment.title = request.form.get('assignment_title', assignment.title)
            assignment.description = request.form.get('assignment_description', assignment.description)
            
            due_date_str = request.form.get('assignment_due_date')
            if due_date_str:
                try:
                    assignment.due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    pass
            else:
                assignment.due_date = None
            
            try:
                assignment.points = int(request.form.get('assignment_points', assignment.points or 100))
            except (ValueError, TypeError):
                pass
            
            assignment.is_published = request.form.get('assignment_published') == 'on'
            
            db.session.commit()
            flash('Assignment updated successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Grade and comment on submission
        elif action == 'grade_submission' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseAssignmentSubmission
            submission_id = request.form.get('submission_id')
            grade = request.form.get('grade')
            comment = request.form.get('comment')
            passed_flag = request.form.get('passed') == 'on'
            
            submission = CourseAssignmentSubmission.query.get(submission_id)
            if submission:
                if grade:
                    submission.grade = int(grade)
                if comment:
                    submission.comment = comment
                submission.passed = passed_flag
                db.session.commit()
                flash('Grade and comment saved successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Decline submission
        elif action == 'decline_submission':
            from lms.models import CourseAssignmentSubmission, CourseAssignment
            submission_id = request.form.get('submission_id')
            
            submission = CourseAssignmentSubmission.query.get(submission_id)
            if not submission:
                flash('Submission not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            assignment = submission.assignment
            # Check permissions: teacher/admin of the course OR the student who submitted
            if not ((current_user.is_teacher or current_user.is_admin) or current_user.id == submission.user_id):
                flash('You do not have permission to decline this submission.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Toggle declined status
            submission.declined = not submission.declined
            db.session.commit()
            if submission.declined:
                flash('Submission declined successfully!', 'success')
            else:
                flash('Declined status cleared!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Submit assignment (student)
        elif action == 'submit_assignment' and current_user.is_authenticated:
            assignment_id = request.form.get('assignment_id')
            uploaded_file = request.files.get('submission_file')
            allow_others_to_view = True  # Always allow viewing for submissions
            
            if not uploaded_file:
                flash('Please select a file to upload.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))

            try:
                validate_upload(uploaded_file, max_bytes=current_app.config['MAX_CONTENT_LENGTH'])
            except UploadValidationError as e:
                flash(str(e), 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))

            # Create temporary directory
            temp_dir = os.path.join('static', 'temp')
            os.makedirs(temp_dir, exist_ok=True)

            # Generate unique filename
            filename = secure_filename(uploaded_file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{current_user.id}_{timestamp}_{filename}"
            temp_file_path = os.path.join(temp_dir, unique_filename)

            # Save the file temporarily
            uploaded_file.save(temp_file_path)
            
            # Upload to Google Drive
            from lms.google_drive_service import authenticate, upload_file, create_view_only_link, set_file_permissions
            service = authenticate()
            if not service:
                flash('Failed to authenticate with Google Drive. Please link your Google account first.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            try:
                drive_file_id = upload_file(service, temp_file_path, filename)
            except Exception as e:
                current_app.logger.error(f"Error uploading to Drive: {e}")
                if "insufficientPermissions" in str(e) or "403" in str(e):
                    flash(Markup('Your Google account does not have sufficient Drive permissions. Please <a href="/auth/link-google-account" class="alert-link">re-link your Google account</a> to grant full Drive access.'), 'error')
                else:
                    flash('Failed to upload file to Google Drive. Please try again.', 'error')
                # Clean up temporary file
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            if not drive_file_id:
                flash('Failed to upload file to Google Drive. Please try again.', 'error')
                # Clean up temporary file
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Try to set permissions, but don't fail if this doesn't work
            if allow_others_to_view:
                try:
                    set_file_permissions(service, drive_file_id, make_public=True)
                except Exception as e:
                    current_app.logger.warning(f"Warning: Could not set file permissions: {e}")
                    # Continue anyway - file is uploaded, just might have restricted permissions
            
            # Create view-only link
            view_link = create_view_only_link(service, drive_file_id, is_image=False)
            if not view_link:
                flash('Failed to create view link.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check if user already has a submission for this assignment
            existing_submission = CourseAssignmentSubmission.query.filter_by(
                assignment_id=int(assignment_id),
                user_id=current_user.id
            ).first()
            
            if existing_submission:
                # Update existing submission
                existing_submission.drive_file_id = drive_file_id
                existing_submission.drive_view_link = view_link
                existing_submission.submitted_at = datetime.now()
                existing_submission.declined = False  # Clear declined status on resubmission
                db.session.commit()
                flash('Assignment resubmitted successfully!', 'success')
            else:
                # Create new submission record
                new_submission = CourseAssignmentSubmission(
                    assignment_id=int(assignment_id),
                    user_id=current_user.id,
                    drive_file_id=drive_file_id,
                    drive_view_link=view_link,
                    submitted_at=datetime.now(),
                    allow_others_to_view=allow_others_to_view
                )
                db.session.add(new_submission)
                db.session.commit()
                flash('Assignment submitted successfully!', 'success')
            
            # Clean up temporary file
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
            
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Add reply to announcement
        elif action == 'add_reply' and current_user.is_authenticated:
            announcement_id = request.form.get('announcement_id')
            parent_reply_id = request.form.get('parent_reply_id')
            message = request.form.get('reply_message')
            
            if not message:
                flash('Reply message cannot be empty.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            new_reply = CourseAnnouncementReply(
                announcement_id=int(announcement_id),
                user_id=current_user.id,
                parent_reply_id=int(parent_reply_id) if parent_reply_id else None,
                message=message,
                created_at=datetime.now()
            )
            db.session.add(new_reply)
            db.session.commit()
            flash('Reply added successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Create folder
        elif action == 'create_folder' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContentFolder
            parent_folder_id = request.form.get('parent_folder_id')
            folder_title = request.form.get('folder_title')
            folder_description = request.form.get('folder_description')
            


            new_folder = CourseContentFolder(
                course_id=course.id,
                parent_folder_id=int(parent_folder_id) if parent_folder_id else None,
                title=folder_title,
                description=folder_description,
                order=0,
                created_at=datetime.now()
            )
            db.session.add(new_folder)
            db.session.commit()
            flash('Folder created successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Upload file to folder
        elif action == 'upload_file' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            file_folder_id = request.form.get('file_folder_id')
            file_title = request.form.get('file_title')
            file_description = request.form.get('file_description')
            is_published = request.form.get('file_published') == 'on'
            allow_others_to_view = request.form.get('allow_others_to_view') == 'on'
            uploaded_file = request.files.get('content_file')
            

            
            if not uploaded_file:
                flash('Please select a file to upload.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))

            try:
                validate_upload(uploaded_file, max_bytes=current_app.config['MAX_CONTENT_LENGTH'])
            except UploadValidationError as e:
                flash(str(e), 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))

            # Create temporary directory
            temp_dir = os.path.join('static', 'temp')
            os.makedirs(temp_dir, exist_ok=True)

            # Generate unique filename
            filename = secure_filename(uploaded_file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            temp_file_path = os.path.join(temp_dir, unique_filename)

            # Save the file temporarily
            uploaded_file.save(temp_file_path)

            # Upload to Google Drive
            from lms.google_drive_service import authenticate, upload_file, create_view_only_link, set_file_permissions
            service = authenticate()
            if not service:
                flash(Markup('Failed to authenticate with Google Drive. Please <a href="/auth/link-google-account" class="alert-link">link your Google account</a> first.'), 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            try:
                drive_file_id = upload_file(service, temp_file_path, filename)
            except Exception as e:
                current_app.logger.error(f"Error uploading to Drive: {e}")
                if "insufficientPermissions" in str(e) or "403" in str(e):
                    flash(Markup('Your Google account does not have sufficient Drive permissions. Please <a href="/auth/link-google-account" class="alert-link">re-link your Google account</a> to grant full Drive access.'), 'error')
                else:
                    flash('Failed to upload file to Google Drive. Please try again.', 'error')
                # Clean up temporary file
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            if not drive_file_id:
                flash('Failed to upload file to Google Drive. Please try again.', 'error')
                # Clean up temporary file
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Try to set permissions, but don't fail if this doesn't work
            if allow_others_to_view:
                try:
                    set_file_permissions(service, drive_file_id, make_public=True)
                except Exception as e:
                    current_app.logger.warning(f"Warning: Could not set file permissions: {e}")
                    # Continue anyway - file is uploaded, just might have restricted permissions
            
            # Create view-only link
            view_link = create_view_only_link(service, drive_file_id, is_image=False)
            if not view_link:
                flash('Failed to create view link.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Create content record
            new_content = CourseContent(
                course_id=course.id,
                folder_id=int(file_folder_id) if file_folder_id else None,
                title=file_title,
                description=file_description,
                content_type='file',
                content_data='',  # Not used for file content
                allow_others_to_view=allow_others_to_view,
                drive_file_id=drive_file_id,
                drive_view_link=view_link,
                is_published=is_published,
                order=0,
                created_at=datetime.now()
            )
            db.session.add(new_content)
            db.session.commit()
            
            # Clean up temporary file
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
            
            flash('File uploaded successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Delete course content
        elif action == 'delete_content' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            from lms.google_drive_service import authenticate, delete_file
            
            content_id = request.form.get('content_id')
            content = CourseContent.query.get(content_id)
            
            if not content:
                flash('Content not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Delete from Google Drive only if the app uploaded it (not imported from user's Drive)
            if content.drive_file_id and not content.is_imported:
                service = authenticate()
                if service:
                    try:
                        delete_file(service, content.drive_file_id)
                    except Exception as e:
                        current_app.logger.error(f"Error deleting file from Google Drive: {e}")

            # Delete from database
            db.session.delete(content)
            db.session.commit()
            flash('Content deleted successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Delete assignment submission
        elif action == 'delete_submission' and current_user.is_authenticated:
            from lms.models import CourseAssignmentSubmission
            from lms.google_drive_service import authenticate, delete_file
            
            submission_id = request.form.get('submission_id')
            submission = CourseAssignmentSubmission.query.get(submission_id)
            
            if not submission:
                flash('Submission not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check permission: must be the owner or an admin
            if submission.user_id != current_user.id and not current_user.is_admin:
                flash('You do not have permission to delete this submission.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Delete from Google Drive
            if submission.drive_file_id:
                service = authenticate()
                if service:
                    try:
                        delete_file(service, submission.drive_file_id)
                    except Exception as e:
                        current_app.logger.error(f"Error deleting file from Google Drive: {e}")
            
            # Delete from database
            db.session.delete(submission)
            db.session.commit()
            flash('Submission deleted successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Toggle content visibility
        elif action == 'toggle_content_visibility' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            from lms.google_drive_service import authenticate, set_file_permissions
            
            content_id = request.form.get('content_id')
            content = CourseContent.query.get(content_id)
            
            if not content:
                flash('Content not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Toggle visibility
            content.allow_others_to_view = not content.allow_others_to_view
            
            # Update Google Drive permissions
            if content.drive_file_id:
                service = authenticate()
                if service:
                    try:
                        set_file_permissions(service, content.drive_file_id, make_public=content.allow_others_to_view)
                    except Exception as e:
                        current_app.logger.error(f"Error updating Drive permissions: {e}")
            
            db.session.commit()
            flash(f"File visibility updated: {'Visible to students' if content.allow_others_to_view else 'Private'}", 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))

        elif action == 'toggle_content_downloadable' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            content_id = request.form.get('content_id')
            content = CourseContent.query.get(content_id)
            if not content:
                flash('Content not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            if content.course_id != course.id:
                flash('Content does not belong to this course.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            content.is_downloadable = not content.is_downloadable
            db.session.commit()
            flash(f"Download {'enabled' if content.is_downloadable else 'disabled'} for \"{content.title}\".", 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))

        # Toggle submission visibility
        elif action == 'toggle_submission_visibility' and current_user.is_authenticated:
            from lms.models import CourseAssignmentSubmission
            from lms.google_drive_service import authenticate, set_file_permissions
            
            submission_id = request.form.get('submission_id')
            submission = CourseAssignmentSubmission.query.get(submission_id)
            
            if not submission:
                flash('Submission not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check permission: must be the owner or an admin
            if submission.user_id != current_user.id and not current_user.is_admin:
                flash('You do not have permission to change this submission visibility.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Toggle visibility
            submission.allow_others_to_view = not submission.allow_others_to_view
            
            # Update Google Drive permissions
            if submission.drive_file_id:
                service = authenticate()
                if service:
                    try:
                        set_file_permissions(service, submission.drive_file_id, make_public=submission.allow_others_to_view)
                    except Exception as e:
                        current_app.logger.error(f"Error updating Drive permissions: {e}")
            
            db.session.commit()
            flash(f"Submission visibility updated: {'Visible to others' if submission.allow_others_to_view else 'Private'}", 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Delete folder
        elif action == 'delete_folder' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContentFolder, CourseContent
            folder_id = request.form.get('folder_id')
            delete_with_contents = request.form.get('delete_with_contents') == '1'
            folder = CourseContentFolder.query.get(folder_id)
            
            if not folder:
                flash('Folder not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check if folder belongs to this course
            if folder.course_id != course.id:
                flash('Folder does not belong to this course.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            def delete_folder_and_contents(folder):
                # Recursively delete all subfolders and their contents
                for subfolder in folder.subfolders:
                    delete_folder_and_contents(subfolder)
                # Delete all files in this folder
                for item in folder.items:
                    db.session.delete(item)
                db.session.delete(folder)

            if delete_with_contents:
                delete_folder_and_contents(folder)
                db.session.commit()
                flash('Folder and all its contents deleted successfully!', 'success')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            else:
                # Check if folder has contents or subfolders
                if len(folder.items) > 0 or len(folder.subfolders) > 0:
                    flash('Cannot delete folder that contains files or subfolders. Please delete them first, or use the delete with contents option.', 'error')
                    return redirect(url_for('main.course_page_enrolled', course_id=course.id))
                db.session.delete(folder)
                db.session.commit()
                flash('Folder deleted successfully!', 'success')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Edit folder
        elif action == 'edit_folder' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContentFolder
            folder_id = request.form.get('folder_id')
            folder_name = request.form.get('folder_name')
            folder_description = request.form.get('folder_description')
            
            folder = CourseContentFolder.query.get(folder_id)
            
            if not folder:
                flash('Folder not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check if folder belongs to this course
            if folder.course_id != course.id:
                flash('Folder does not belong to this course.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Update folder
            folder.title = folder_name
            folder.description = folder_description
            db.session.commit()
            flash('Folder updated successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Edit file
        elif action == 'edit_file' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            file_id = request.form.get('file_id')
            file_name = request.form.get('file_name')
            file_description = request.form.get('file_description')
            
            content = CourseContent.query.get(file_id)
            
            if not content:
                flash('File not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check if file belongs to this course
            if content.course_id != course.id:
                flash('File does not belong to this course.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Update file
            content.title = file_name
            content.description = file_description
            db.session.commit()
            flash('File updated successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Delete assignment
        elif action == 'delete_assignment' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseAssignment
            from lms.google_drive_service import authenticate, delete_file
            assignment_id = request.form.get('assignment_id')
            if not assignment_id:
                flash('Invalid assignment ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            try:
                assignment_id = int(assignment_id)
            except (ValueError, TypeError):
                flash('Invalid assignment ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))

            assignment = CourseAssignment.query.get(assignment_id)
            
            if not assignment:
                flash('Assignment not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check if assignment belongs to this course
            if assignment.course_id != course.id:
                flash('Assignment does not belong to this course.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Delete all submissions first
            for submission in assignment.submissions:
                # Delete from Google Drive
                if submission.drive_file_id:
                    service = authenticate()
                    if service:
                        try:
                            delete_file(service, submission.drive_file_id)
                        except Exception as e:
                            current_app.logger.error(f"Error deleting submission file from Google Drive: {e}")
                db.session.delete(submission)
            
            # Delete assignment
            db.session.delete(assignment)
            db.session.commit()
            flash('Assignment deleted successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Delete announcement
        elif action == 'delete_announcement' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseAnnouncement
            announcement_id = request.form.get('announcement_id')
            announcement = CourseAnnouncement.query.get(announcement_id)
            
            if not announcement:
                flash('Announcement not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check if announcement belongs to this course
            if announcement.course_id != course.id:
                flash('Announcement does not belong to this course.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Delete all replies first
            for reply in announcement.replies:
                db.session.delete(reply)
            
            # Delete announcement
            db.session.delete(announcement)
            db.session.commit()
            flash('Announcement deleted successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Add review
        elif action == 'add_review' and current_user.is_authenticated:
            rating = request.form.get('rating')
            review_title = request.form.get('review_title')
            review_text = request.form.get('review_text')
            
            if not rating or not review_title or not review_text:
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check if user already reviewed this course
            existing_review = CourseReview.query.filter_by(course_id=course.id, user_id=current_user.id).first()
            if existing_review:
                flash('You have already reviewed this course. You can edit your existing review.', 'warning')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            new_review = CourseReview(
                course_id=course.id,
                user_id=current_user.id,
                rating=int(rating),
                title=review_title,
                review_text=review_text
            )
            db.session.add(new_review)
            db.session.commit()
            flash('Review submitted successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Edit review
        elif action == 'edit_review' and current_user.is_authenticated:
            review_id = request.form.get('review_id')
            rating = request.form.get('rating')
            review_title = request.form.get('review_title')
            review_text = request.form.get('review_text')
            
            review = CourseReview.query.get(review_id)
            if not review:
                flash('Review not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check permission: must be the owner or an admin/teacher
            if review.user_id != current_user.id and not (current_user.is_teacher or current_user.is_admin):
                flash('You do not have permission to edit this review.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Update only the fields that should change, preserve course_id and user_id
            review.rating = int(rating)
            review.title = review_title
            review.review_text = review_text
            # Explicitly preserve relationships
            db.session.add(review)
            db.session.commit()
            flash('Review updated successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Delete review
        elif action == 'delete_review' and current_user.is_authenticated:
            review_id = request.form.get('review_id')
            review = CourseReview.query.get(review_id)
            
            if not review:
                flash('Review not found.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Check permission: must be the owner or an admin/teacher
            if review.user_id != current_user.id and not (current_user.is_teacher or current_user.is_admin):
                flash('You do not have permission to delete this review.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            db.session.delete(review)
            db.session.commit()
            flash('Review deleted successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Import single file from Google Drive
        elif action == 'import_drive_file' and (current_user.is_teacher or current_user.is_admin):
            drive_url = request.form.get('drive_url', '').strip()
            current_app.logger.debug(f"import_drive_file action called with drive_url: {drive_url}")
            if not drive_url:
                flash('Please provide a Google Drive file URL or ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            from lms.google_drive_service import authenticate, import_drive_file
            service = authenticate()
            current_app.logger.debug(f"authenticate() returned: {service is not None}")
            if not service:
                flash(Markup('Failed to authenticate with Google Drive. Please <a href="/auth/link-google-account" class="alert-link">link your Google account</a> first.'), 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            file_data = import_drive_file(service, drive_url)
            current_app.logger.debug(f"import_drive_file() returned: {file_data}")
            if isinstance(file_data, dict) and 'error' in file_data:
                error_msg = file_data["error"]
                if 'error_code' in file_data and file_data['error_code'] == 404:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                elif 'error_code' in file_data and file_data['error_code'] == 403:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                flash(f'Import failed: {error_msg}', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            elif not file_data:
                flash(Markup('Failed to import file from Google Drive. Please check the URL and permissions. <a href="/auth/google-account-info" class="alert-link">Check linked account</a>'), 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Optional folder assignment
            folder_id = request.form.get('import_folder_id')
            
            content = CourseContent(
                course_id=course.id,
                title=request.form.get('import_title') or file_data['name'],
                description='',
                content_type='file',
                content_data=file_data['view_link'],
                drive_file_id=file_data['file_id'],
                drive_view_link=file_data['view_link'],
                order=CourseContent.query.filter_by(course_id=course.id).count() + 1,
                folder_id=int(folder_id) if folder_id else None,
                is_published=request.form.get('import_published') == 'on',
                allow_others_to_view=request.form.get('import_allow_view') == 'on',
                is_imported=True
            )
            current_app.logger.debug(f"Created CourseContent object: {content.title}, drive_file_id: {content.drive_file_id}")
            db.session.add(content)
            current_app.logger.debug("Added content to session")
            db.session.commit()
            current_app.logger.debug("Committed to database")
            flash(f'Successfully imported: {file_data["name"]}', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Import entire folder from Google Drive
        elif action == 'import_drive_folder' and (current_user.is_teacher or current_user.is_admin):
            folder_url = request.form.get('drive_url', '').strip()
            current_app.logger.debug(f"import_drive_folder action called with folder_url: {folder_url}")
            if not folder_url:
                flash('Please provide a Google Drive folder URL or ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            from lms.google_drive_service import authenticate, import_drive_folder
            service = authenticate()
            current_app.logger.debug(f"authenticate() returned: {service is not None}")
            if not service:
                flash(Markup('Failed to authenticate with Google Drive. Please <a href="/auth/link-google-account" class="alert-link">link your Google account</a> first.'), 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            folder_data = import_drive_folder(service, folder_url)
            current_app.logger.debug(f"import_drive_folder() returned: {folder_data}")
            if isinstance(folder_data, dict) and 'error' in folder_data:
                error_msg = folder_data["error"]
                if 'error_code' in folder_data and folder_data['error_code'] == 404:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                elif 'error_code' in folder_data and folder_data['error_code'] == 403:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                flash(f'Import failed: {error_msg}', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            elif not folder_data:
                flash(Markup('Failed to import folder from Google Drive. Please check the URL and ensure it\'s a folder. <a href="/auth/google-account-info" class="alert-link">Check linked account</a>'), 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            
            # Create nested folder structure recursively
            def create_course_folders_recursive(folder_structure, parent_folder_id=None, base_path=""):
                """Recursively create course folders and add files"""
                created_folders = {}
                total_files = 0
                
                # Create subfolders first
                for folder_info in folder_structure['folders']:
                    folder_path = f"{base_path}/{folder_info['name']}" if base_path else folder_info['name']
                    
                    # Create course folder
                    course_subfolder = CourseContentFolder(
                        course_id=course.id,
                        title=folder_info['name'],
                        description=f'Imported from Google Drive: {folder_path}',
                        order=CourseContentFolder.query.filter_by(course_id=course.id).count() + 1,
                        parent_folder_id=parent_folder_id
                    )
                    db.session.add(course_subfolder)
                    db.session.flush()
                    
                    created_folders[folder_path] = course_subfolder.id
                    
                    # Recursively process subfolder contents
                    sub_files = create_course_folders_recursive(
                        folder_info['structure'], 
                        course_subfolder.id, 
                        folder_path
                    )
                    total_files += sub_files
                
                # Add files to current folder level
                for file_data in folder_structure['files']:
                    content = CourseContent(
                        course_id=course.id,
                        title=file_data['name'],
                        description=f'Imported from Google Drive: {file_data["full_path"]}',
                        content_type='file',
                        content_data=file_data['view_link'],
                        drive_file_id=file_data['file_id'],
                        drive_view_link=file_data['view_link'],
                        order=CourseContent.query.filter_by(course_id=course.id).count() + 1,
                        folder_id=parent_folder_id,
                        is_published=request.form.get('import_published') == 'on',
                        allow_others_to_view=True,
                        is_imported=True
                    )
                    db.session.add(content)
                    total_files += 1
                
                return total_files
            
            # Create the root course folder
            root_course_folder = CourseContentFolder(
                course_id=course.id,
                title=folder_data['folder_name'],
                description='Imported from Google Drive folder',
                order=CourseContentFolder.query.filter_by(course_id=course.id).count() + 1
            )
            db.session.add(root_course_folder)
            db.session.flush()
            
            current_app.logger.debug(f"Created root course folder: {root_course_folder.title}, id: {root_course_folder.id}")
            
            # Reconstruct folder structure from flat file list
            folder_structure = {'folders': [], 'files': []}
            folder_map = {}
            
            # Group files by their folder paths
            for file_data in folder_data['files']:
                folder_path = file_data.get('folder_path', '')
                
                if folder_path:
                    # This file is in a subfolder
                    if folder_path not in folder_map:
                        folder_map[folder_path] = {'folders': [], 'files': []}
                    folder_map[folder_path]['files'].append(file_data)
                else:
                    # This file is in the root folder
                    folder_structure['files'].append(file_data)
            
            # Build nested structure (simplified - assuming no deeply nested empty folders)
            def build_nested_structure():
                # For simplicity, we'll put all files in their respective folders
                # This is a simplified approach - in a full implementation you'd rebuild the tree
                pass
            
            # Add files to appropriate folders
            imported_count = 0
            current_folder_id = root_course_folder.id
            
            # Add root level files
            for file_data in folder_data['files']:
                folder_path = file_data.get('folder_path', '')
                
                if not folder_path:
                    # Root level file
                    content = CourseContent(
                        course_id=course.id,
                        title=file_data['name'],
                        description=f'Imported from Google Drive: {file_data.get("full_path", file_data["name"])}',
                        content_type='file',
                        content_data=file_data['view_link'],
                        drive_file_id=file_data['file_id'],
                        drive_view_link=file_data['view_link'],
                        order=imported_count + 1,
                        folder_id=current_folder_id,
                        is_published=request.form.get('import_published') == 'on',
                        allow_others_to_view=True,
                        is_imported=True
                    )
                    db.session.add(content)
                    imported_count += 1
            
            # For subfolders, create them and add their files
            subfolder_files = [f for f in folder_data['files'] if f.get('folder_path')]
            if subfolder_files:
                # Group by immediate parent folder
                folder_groups = {}
                for file_data in subfolder_files:
                    folder_path = file_data.get('folder_path', '')
                    if folder_path:
                        parent_folder = folder_path.split('/')[0]  # Get immediate parent
                        if parent_folder not in folder_groups:
                            folder_groups[parent_folder] = []
                        folder_groups[parent_folder].append(file_data)
                
                # Create subfolders and add files
                for subfolder_name, files in folder_groups.items():
                    subfolder = CourseContentFolder(
                        course_id=course.id,
                        title=subfolder_name,
                        description='Subfolder imported from Google Drive',
                        order=CourseContentFolder.query.filter_by(course_id=course.id).count() + 1,
                        parent_folder_id=current_folder_id
                    )
                    db.session.add(subfolder)
                    db.session.flush()
                    
                    for file_data in files:
                        content = CourseContent(
                            course_id=course.id,
                            title=file_data['name'],
                            description=f'Imported from Google Drive: {file_data.get("full_path", file_data["name"])}',
                            content_type='file',
                            content_data=file_data['view_link'],
                            drive_file_id=file_data['file_id'],
                            drive_view_link=file_data['view_link'],
                            order=imported_count + 1,
                            folder_id=subfolder.id,
                            is_published=request.form.get('import_published') == 'on',
                            allow_others_to_view=True
                        )
                        db.session.add(content)
                        imported_count += 1
            
            current_app.logger.debug(f"Added {imported_count} content items to session")
            db.session.commit()
            current_app.logger.debug("Committed recursive folder import to database")
            flash(f'Successfully imported folder "{folder_data["folder_name"]}" with {imported_count} files from all subfolders!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Bulk delete content
        elif action == 'bulk_delete_content' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent, CourseContentFolder
            from lms.google_drive_service import authenticate, delete_file

            content_ids = request.form.getlist('content_ids')
            folder_ids = request.form.getlist('folder_ids')
            deleted_count = 0

            for content_id in content_ids:
                content_id = content_id.strip()
                if not content_id or not content_id.isdigit():
                    continue
                content = CourseContent.query.get(int(content_id))
                if content and content.course_id == course.id:
                    if content.drive_file_id and not content.is_imported:
                        service = authenticate()
                        if service:
                            try:
                                delete_file(service, content.drive_file_id)
                            except Exception as e:
                                current_app.logger.error(f"Error deleting file from Google Drive: {e}")
                    db.session.delete(content)
                    deleted_count += 1

            def _delete_folder_recursive(folder):
                for subfolder in list(folder.subfolders):
                    _delete_folder_recursive(subfolder)
                for item in list(folder.items):
                    db.session.delete(item)
                db.session.delete(folder)

            for folder_id in folder_ids:
                folder_id = folder_id.strip()
                if not folder_id or not folder_id.isdigit():
                    continue
                folder = CourseContentFolder.query.get(int(folder_id))
                if folder and folder.course_id == course.id:
                    _delete_folder_recursive(folder)
                    deleted_count += 1

            db.session.commit()
            flash(f'{deleted_count} items deleted successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Reorder files in a folder
        elif action == 'reorder_files' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            folder_id = request.form.get('folder_id')
            file_order = request.form.get('file_order', '')
            if folder_id and file_order:
                file_ids = [int(fid) for fid in file_order.split(',') if fid.isdigit()]
                for idx, file_id in enumerate(file_ids):
                    content = CourseContent.query.get(file_id)
                    if content and content.folder_id == int(folder_id) and content.course_id == course.id:
                        content.order = idx
                db.session.commit()
                flash('File order updated!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))

        # Reorder root-level folders (drag-and-drop from course page)
        elif action == 'reorder_root_folders' and (current_user.is_teacher or current_user.is_admin):
            folder_order = request.form.get('folder_order', '')
            if folder_order:
                folder_ids = [int(fid) for fid in folder_order.split(',') if fid.isdigit()]
                for idx, folder_id in enumerate(folder_ids):
                    folder = CourseContentFolder.query.get(folder_id)
                    if folder and folder.course_id == course.id and folder.parent_folder_id is None:
                        folder.order = idx + 1
                db.session.commit()
                flash('Root folder order updated!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))

        # Reorder subfolders in a folder
        elif action == 'reorder_folders' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContentFolder
            parent_folder_id = request.form.get('parent_folder_id')
            folder_order = request.form.get('folder_order', '')
            if parent_folder_id is not None and folder_order:
                folder_ids = [int(fid) for fid in folder_order.split(',') if fid.isdigit()]
                for idx, folder_id in enumerate(folder_ids):
                    folder = CourseContentFolder.query.get(folder_id)
                    if folder and str(folder.parent_folder_id or '') == str(parent_folder_id) and folder.course_id == course.id:
                        folder.order = idx
                db.session.commit()
                flash('Folder order updated!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Bulk move content
        elif action == 'bulk_move_content' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent, CourseContentFolder

            content_ids_raw = request.form.get('selected_ids', '')
            content_ids = [cid.strip() for cid in content_ids_raw.split(',') if cid.strip().isdigit()]
            folder_ids_raw = request.form.get('folder_ids', '')
            folder_ids = [fid.strip() for fid in folder_ids_raw.split(',') if fid.strip().isdigit()]
            target_folder_id = request.form.get('target_folder_id')
            moved_count = 0

            if not content_ids and not folder_ids:
                flash('No valid items selected for moving.', 'warning')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))

            target_id_int = int(target_folder_id) if target_folder_id else None

            for content_id in content_ids:
                content = CourseContent.query.get(int(content_id))
                if content and content.course_id == course.id:
                    content.folder_id = target_id_int
                    moved_count += 1

            for folder_id in folder_ids:
                folder = CourseContentFolder.query.get(int(folder_id))
                if folder and folder.course_id == course.id and folder.id != target_id_int:
                    if target_id_int and _folder_is_ancestor_of(folder.id, target_id_int):
                        continue
                    folder.parent_folder_id = target_id_int
                    moved_count += 1

            db.session.commit()
            flash(f'{moved_count} items moved successfully!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        
        # Import assignment into folder as content
        elif action == 'import_assignment' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent, CourseAssignment
            assignment_id = request.form.get('assignment_id')
            folder_id = request.form.get('import_assignment_folder_id')
            lock_assignment_id = request.form.get('import_assignment_lock_assignment_id')
            lock_folder_ids = request.form.getlist('import_lock_folder_ids')
            if not assignment_id:
                flash('Invalid assignment ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            try:
                assignment_id = int(assignment_id)
            except (ValueError, TypeError):
                flash('Invalid assignment ID.', 'error')
                return redirect(url_for('main.course_page_enrolled', course_id=course.id))
            assignment = CourseAssignment.query.get(assignment_id)
            if assignment and assignment.course_id == course.id:
                # Prevent importing the same assignment into course content more than once
                existing = CourseContent.query.filter_by(course_id=course.id, content_type='assignment', content_data=str(assignment.id)).first()
                if existing:
                    flash(f'Assignment "{assignment.title}" has already been imported to course content.', 'warning')
                    return redirect(url_for('main.course_page_enrolled', course_id=course.id))
                content = CourseContent(
                    course_id=course.id,
                    title=assignment.title,
                    description=assignment.description,
                    content_type='assignment',
                    content_data=str(assignment.id),
                    folder_id=int(folder_id) if folder_id else None,
                    is_published=request.form.get('import_assignment_published') == 'on',
                    allow_others_to_view=True
                )
                db.session.add(content)
                db.session.commit()
                # If a lock assignment was chosen, lock selected folders (or all other folders if none selected)
                try:
                    if lock_assignment_id:
                        lock_id_int = int(lock_assignment_id)
                        from lms.models import CourseContentFolder
                        if lock_folder_ids:
                            # lock only the explicitly selected folders
                            for fid in lock_folder_ids:
                                if fid and fid.isdigit():
                                    f = CourseContentFolder.query.get(int(fid))
                                    if f and f.course_id == course.id:
                                        f.locked_until_assignment_id = lock_id_int
                        else:
                            # default: lock all other folders except destination
                            other_folders = CourseContentFolder.query.filter_by(course_id=course.id).all()
                            for f in other_folders:
                                if folder_id and f.id == int(folder_id):
                                    continue
                                f.locked_until_assignment_id = lock_id_int
                        db.session.commit()
                except ValueError:
                    pass
                flash(f'Assignment "{assignment.title}" imported to folder!', 'success')
            else:
                flash('Assignment not found or does not belong to this course.', 'danger')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))
        # Bulk toggle visibility
        elif action == 'bulk_toggle_visibility' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            
            content_ids = request.form.getlist('content_ids')
            toggled_count = 0
            for content_id in content_ids:
                content_id = content_id.strip()
                if not content_id or not content_id.isdigit():
                    continue
                content = CourseContent.query.get(int(content_id))
                if content and content.course_id == course.id:
                    content.is_published = not content.is_published
                    toggled_count += 1
            db.session.commit()
            flash(f'Visibility toggled for {toggled_count} items!', 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))

        elif action == 'give_certificate' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import Certificate, User
            from datetime import datetime as _dt
            student_id = request.form.get('student_id', type=int)
            student = User.query.get(student_id)
            if not student:
                flash('Student not found.', 'error')
            elif not student.first_name or not student.last_name:
                flash(f'{student.username} has not set their full name yet.', 'warning')
            elif Certificate.query.filter_by(user_id=student_id, course_id=course.id, revoked=False).first():
                flash(_('Certificate already issued to this student.'), 'info')
            else:
                date_mode = request.form.get('date_mode', 'current')
                issued_at = _dt.utcnow()
                if date_mode == 'custom':
                    raw_date = request.form.get('issue_date', '').strip()
                    try:
                        issued_at = _dt.strptime(raw_date, '%Y-%m-%d')
                    except ValueError:
                        flash(_('Invalid date format.'), 'error')
                        return redirect(url_for('main.course_page_enrolled', course_id=course.id))
                cert = Certificate(
                    user_id=student_id,
                    course_id=course.id,
                    issued_by=current_user.id,
                    issued_at=issued_at,
                    student_name=f"{student.first_name} {student.last_name}",
                )
                db.session.add(cert)
                db.session.commit()
                flash(_('Certificate issued to %(name)s.', name=cert.student_name), 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))

        elif action == 'revoke_certificate' and current_user.is_admin:
            from lms.models import Certificate
            from datetime import datetime as _dt
            student_id = request.form.get('student_id', type=int)
            cert = Certificate.query.filter_by(user_id=student_id, course_id=course.id, revoked=False).first()
            if cert:
                cert.revoked = True
                cert.revoked_by = current_user.id
                cert.revoked_at = _dt.utcnow()
                db.session.commit()
                from lms.certificate_generator import invalidate_cache
                invalidate_cache(cert.id)
                flash(_('Certificate revoked.'), 'success')
            return redirect(url_for('main.course_page_enrolled', course_id=course.id))

    # GET request - render the page
    from flask_babel import get_locale
    current_locale = str(get_locale())

    # Get translated title
    from lms.content_translator import get_translated_content
    translated_title = get_translated_content('course', course.id, 'title', course.title, current_locale)

    # PERFORMANCE OPTIMIZATION: Use eager loading to avoid N+1 queries
    # Load all related data in a single query where possible
    from sqlalchemy.orm import joinedload, subqueryload

    # Only one page for course content (no pagination)
    assignment_page = request.args.get('assignment_page', 1, type=int)
    announcement_page = request.args.get('announcement_page', 1, type=int)
    review_page = request.args.get('review_page', 1, type=int)

    # Items per page for assignments, announcements, reviews
    per_page = 10  # Can be adjusted or made configurable

    # Check if user is teacher or admin (needed for content filtering below)
    is_teacher_or_admin = current_user.is_authenticated and (current_user.is_teacher or current_user.is_admin)

    # Load all course content with folders using eager loading (no pagination)
    # Non-teacher/admin students only see files that the teacher has made visible (allow_others_to_view=True)
    _content_query = CourseContent.query.filter_by(course_id=course.id, is_published=True)
    if not is_teacher_or_admin:
        _content_query = _content_query.filter_by(allow_others_to_view=True)
    contents = _content_query.options(
        subqueryload(CourseContent.folder)
    ).order_by(CourseContent.order).all()

    # Load all folders and wire the parent→children tree manually.
    # subqueryload on a self-referential relationship only populates one level,
    # so folders nested 2+ levels deep lose their children after a redirect.
    content_folders = CourseContentFolder.query.filter_by(
        course_id=course.id
    ).order_by(CourseContentFolder.order).all()

    folder_map = {f.id: f for f in content_folders}
    for f in content_folders:
        f._children = []
    for f in content_folders:
        if f.parent_folder_id and f.parent_folder_id in folder_map:
            folder_map[f.parent_folder_id]._children.append(f)

    root_folders = [f for f in content_folders if f.parent_folder_id is None]

    # Load assignments with eager-loaded submissions and pagination
    assignments_pagination = CourseAssignment.query.filter_by(course_id=course.id, is_published=True).options(
        subqueryload(CourseAssignment.submissions)
    ).order_by(CourseAssignment.due_date).paginate(
        page=assignment_page, per_page=per_page, error_out=False
    )
    assignments = assignments_pagination.items

    # Load announcements with eager-loaded replies and users and pagination
    # We'll filter replies in Python for simplicity, but limit the data loaded
    announcements_pagination = CourseAnnouncement.query.filter_by(course_id=course.id, is_published=True).options(
        joinedload(CourseAnnouncement.author),
        subqueryload(CourseAnnouncement.replies).joinedload(CourseAnnouncementReply.user)
    ).order_by(CourseAnnouncement.created_at.desc()).paginate(
        page=announcement_page, per_page=per_page, error_out=False
    )
    announcements = announcements_pagination.items

    # Load reviews with eager-loaded users and pagination
    reviews_pagination = CourseReview.query.filter_by(course_id=course.id).options(
        joinedload(CourseReview.user)
    ).order_by(CourseReview.created_at.desc()).paginate(
        page=review_page, per_page=per_page, error_out=False
    )
    reviews = reviews_pagination.items
    
    # Get passed assignment IDs for current user (for folder locking)
    passed_subs = []
    if current_user.is_authenticated:
        passed_subs = CourseAssignmentSubmission.query.filter_by(
            user_id=current_user.id,
            passed=True
        ).all()

    # Get passed quiz IDs for current user (for folder locking) + this course's quizzes
    from lms.models import Quiz, QuizAttempt
    passed_quiz_attempts = []
    if current_user.is_authenticated:
        passed_quiz_attempts = (QuizAttempt.query
                                 .join(Quiz)
                                 .filter(QuizAttempt.user_id == current_user.id,
                                         Quiz.course_id == course.id,
                                         QuizAttempt.passed.is_(True))
                                 .all())
    quizzes = Quiz.query.filter_by(course_id=course.id, is_published=True).all()

    # Get home content
    site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    
    # Generate folder paths for dropdown menus
    folder_paths = {folder.id: folder.title for folder in content_folders}

    # Certificate data
    from lms.models import Certificate
    my_certificate = None
    cert_students = []
    if current_user.is_authenticated:
        if is_teacher_or_admin:
            enrolled_students = course.users
            for student in enrolled_students:
                cert = Certificate.query.filter_by(user_id=student.id, course_id=course.id, revoked=False).first()
                cert_students.append({'user': student, 'certificate': cert})
        else:
            my_certificate = Certificate.query.filter_by(
                user_id=current_user.id, course_id=course.id, revoked=False
            ).first()
    issued_certs = Certificate.query.filter_by(course_id=course.id, revoked=False).all()
    cert_graduates = [
        {'name': c.student_name, 'date': c.issued_at.strftime('%d %b %Y'), 'city': (c.user.city or '') if c.user else ''}
        for c in issued_certs
        if c.student_name
    ]

    return render_template('course_page_enrolled.html',
        course=course,
        site_settings=site_settings,
        is_authenticated=current_user.is_authenticated,
        current_user=current_user,
        current_locale=str(get_locale()),
        enrolled=enrolled,
        is_teacher_or_admin=is_teacher_or_admin,
        contents=contents,
        content_folders=content_folders,
        root_folders=root_folders,
        assignments=assignments,
        assignments_pagination=assignments_pagination,
        announcements=announcements,
        announcements_pagination=announcements_pagination,
        reviews=reviews,
        reviews_pagination=reviews_pagination,
        passed_assignment_ids=[sub.assignment_id for sub in passed_subs],
        passed_quiz_ids=[a.quiz_id for a in passed_quiz_attempts],
        quizzes=quizzes,
        folder_paths=folder_paths,
        translated_title=translated_title,
        datetime=dt,
        now=dt.utcnow(),
        my_certificate=my_certificate,
        cert_students=cert_students,
        cert_graduates=cert_graduates,
    )


@main_bp.route('/site')
def serve_site():
    """Serve site page"""
    return render_template('index.html')

@main_bp.route('/courses')
def courses():
    """Serve courses page"""
    from lms.models import SiteSettings
    try:
        site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    except Exception as e:
        current_app.logger.error(f"Database error in courses route: {e}")
        site_settings = SiteSettings()
    return render_template('index.html', 
                         is_authenticated=current_user.is_authenticated, 
                         site_settings=site_settings, initial_page='courses')

@main_bp.route('/forum')
def forum():
    """Serve forum page"""
    from lms.models import SiteSettings
    try:
        site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    except Exception as e:
        current_app.logger.error(f"Database error in forum route: {e}")
        site_settings = SiteSettings()
    return render_template('index.html', 
                         is_authenticated=current_user.is_authenticated, 
                         site_settings=site_settings, initial_page='forum')

@main_bp.route('/resources')
def resources():
    """Serve resources page"""
    from lms.models import SiteSettings
    try:
        site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    except Exception as e:
        current_app.logger.error(f"Database error in resources route: {e}")
        site_settings = SiteSettings()
    return render_template('index.html', 
                         is_authenticated=current_user.is_authenticated, 
                         site_settings=site_settings, initial_page='resources')

@main_bp.route('/moxo-test')
def moxo_test():
    """Serve MOXO test page"""
    from lms.models import SiteSettings
    try:
        site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    except Exception as e:
        current_app.logger.error(f"Database error in moxo-test route: {e}")
        site_settings = SiteSettings()
    return render_template('index.html', 
                         is_authenticated=current_user.is_authenticated, 
                         site_settings=site_settings, initial_page='moxo-test')

@main_bp.route('/about')
def about():
    """Serve about page"""
    from lms.models import SiteSettings
    try:
        site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    except Exception as e:
        current_app.logger.error(f"Database error in about route: {e}")
        site_settings = SiteSettings()
    return render_template('index.html', 
                         is_authenticated=current_user.is_authenticated, 
                         site_settings=site_settings, initial_page='about')

@main_bp.route('/terms')
def terms():
    """Serve terms of service page"""
    return render_template('terms.html')

@main_bp.route('/privacy')
@main_bp.route('/privacy-policy')
def privacy():
    """Serve privacy policy page"""
    return render_template('privacyPolicy.html')

@main_bp.route('/course/<slug>/edit', methods=['GET', 'POST'])
@login_required
def edit_course_page(slug):
    """Blackboard-style course editor for content, assignments, and announcements"""
    from lms.models import Course, CourseContent, CourseAssignment, CourseAnnouncement, db
    from slugify import slugify
    from datetime import datetime
    
    # Check if user is admin
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.index'))
    
    # Find course by slug
    courses = Course.query.all()
    course = None
    for c in courses:
        if slugify(c.title) == slug:
            course = c
            break
    
    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('main.index'))
    
    # Handle POST requests for adding/updating content
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_content':
            # Handle file upload
            uploaded_file = request.files.get('content_file')
            if not uploaded_file:
                flash('No file was uploaded.', 'error')
                return redirect(request.url, code=303)

            try:
                validate_upload(uploaded_file, max_bytes=current_app.config['MAX_CONTENT_LENGTH'])
            except UploadValidationError as e:
                flash(str(e), 'error')
                return redirect(request.url, code=303)

            # Create temporary directory
            temp_dir = os.path.join('static', 'temp')
            os.makedirs(temp_dir, exist_ok=True)

            # Generate unique filename
            filename = secure_filename(uploaded_file.filename)
            timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            temp_file_path = os.path.join(temp_dir, unique_filename)

            # Save the file temporarily
            uploaded_file.save(temp_file_path)
            
            # Upload to Google Drive
            from lms.google_drive_service import authenticate, upload_file, create_view_only_link
            service = authenticate()
            if not service:
                flash(Markup('Failed to authenticate with Google Drive. Please <a href="/auth/link-google-account" class="alert-link">link your Google account</a> first.'), 'error')
                return redirect(request.url, code=303)
            
            try:
                drive_file_id = upload_file(service, temp_file_path, filename)
            except Exception as e:
                current_app.logger.error(f"Error uploading to Drive: {e}")
                if "insufficientPermissions" in str(e) or "403" in str(e):
                    flash(Markup('Your Google account does not have sufficient Drive permissions. Please <a href="/auth/link-google-account" class="alert-link">re-link your Google account</a> to grant full Drive access.'), 'error')
                else:
                    flash('Failed to upload file to Google Drive. Please try again.', 'error')
                # Clean up temporary file
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
                return redirect(request.url, code=303)
            
            if not drive_file_id:
                flash('Failed to upload file to Google Drive. Please try again.', 'error')
                # Clean up temporary file
                try:
                    os.remove(temp_file_path)
                except Exception:
                    pass
                return redirect(request.url, code=303)
            
            # Create view-only link
            view_link = create_view_only_link(service, drive_file_id, is_image=False)
            if not view_link:
                flash('Failed to create view link.', 'error')
                return redirect(request.url, code=303)
            
            # Clean up temporary file
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
            
            # Optional folder assignment
            folder_id = request.form.get('content_folder_id')

            content = CourseContent(
                course_id=course.id,
                title=request.form.get('content_title', ''),
                description=request.form.get('content_description', ''),
                content_type=request.form.get('content_type', 'file'),
                content_data=view_link,  # Store the Google Drive view link
                drive_file_id=drive_file_id,
                drive_view_link=view_link,
                order=CourseContent.query.filter_by(course_id=course.id).count() + 1,
                folder_id=int(folder_id) if folder_id else None,
                is_published=request.form.get('content_published') == 'on'
            )
            db.session.add(content)
            db.session.commit()
            flash('Content added successfully!', 'success')
            
        elif action == 'import_drive_file':
            # Import a single file from Google Drive
            drive_url = request.form.get('drive_url', '').strip()
            current_app.logger.debug(f"import_drive_file action called with drive_url: {drive_url}")
            if not drive_url:
                flash('Please provide a Google Drive file URL or ID.', 'error')
                return redirect(request.url, code=303)
            
            from lms.google_drive_service import authenticate, import_drive_file
            service = authenticate()
            current_app.logger.debug(f"authenticate() returned: {service is not None}")
            if not service:
                flash(Markup('Failed to authenticate with Google Drive. Please <a href="/auth/link-google-account" class="alert-link">link your Google account</a> first.'), 'error')
                return redirect(request.url, code=303)
            
            file_data = import_drive_file(service, drive_url)
            current_app.logger.debug(f"import_drive_file() returned: {file_data}")
            if isinstance(file_data, dict) and 'error' in file_data:
                error_msg = file_data["error"]
                if 'error_code' in file_data and file_data['error_code'] == 404:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                elif 'error_code' in file_data and file_data['error_code'] == 403:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                flash(f'Import failed: {error_msg}', 'error')
                return redirect(request.url, code=303)
            elif not file_data:
                flash(Markup('Failed to import file from Google Drive. Please check the URL and permissions. <a href="/auth/google-account-info" class="alert-link">Check linked account</a>'), 'error')
                return redirect(request.url, code=303)
            
            # Optional folder assignment
            folder_id = request.form.get('import_folder_id')
            
            content = CourseContent(
                course_id=course.id,
                title=request.form.get('import_title') or file_data['name'],
                description='',
                content_type='file',
                content_data=file_data['view_link'],
                drive_file_id=file_data['file_id'],
                drive_view_link=file_data['view_link'],
                order=CourseContent.query.filter_by(course_id=course.id).count() + 1,
                folder_id=int(folder_id) if folder_id else None,
                is_published=request.form.get('import_published') == 'on',
                allow_others_to_view=request.form.get('import_allow_view') == 'on',
                is_imported=True
            )
            current_app.logger.debug(f"Created CourseContent object: {content.title}, drive_file_id: {content.drive_file_id}")
            db.session.add(content)
            current_app.logger.debug("Added content to session")
            db.session.commit()
            current_app.logger.debug("Committed to database")
            flash(f'Successfully imported: {file_data["name"]}', 'success')
            
        elif action == 'import_drive_folder':
            # Import entire folder from Google Drive
            folder_url = request.form.get('drive_url', '').strip()
            current_app.logger.debug(f"import_drive_folder action called with folder_url: {folder_url}")
            if not folder_url:
                flash('Please provide a Google Drive folder URL or ID.', 'error')
                return redirect(request.url, code=303)

            from lms.models import CourseContentFolder
            from lms.google_drive_service import authenticate, import_drive_folder
            service = authenticate()
            current_app.logger.debug(f"authenticate() returned: {service is not None}")
            if not service:
                flash(Markup('Failed to authenticate with Google Drive. Please <a href="/auth/link-google-account" class="alert-link">link your Google account</a> first.'), 'error')
                return redirect(request.url, code=303)
            
            folder_data = import_drive_folder(service, folder_url)
            current_app.logger.debug(f"import_drive_folder() returned: {folder_data}")
            if isinstance(folder_data, dict) and 'error' in folder_data:
                error_msg = folder_data["error"]
                if 'error_code' in folder_data and folder_data['error_code'] == 404:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                elif 'error_code' in folder_data and folder_data['error_code'] == 403:
                    error_msg += Markup(' <a href="/auth/google-account-info" class="alert-link">Check linked account</a>')
                flash(f'Import failed: {error_msg}', 'error')
                return redirect(request.url, code=303)
            elif not folder_data:
                flash(Markup('Failed to import folder from Google Drive. Please check the URL and ensure it\'s a folder. <a href="/auth/google-account-info" class="alert-link">Check linked account</a>'), 'error')
                return redirect(request.url, code=303)
            
            # Create nested folder structure recursively
            def create_course_folders_recursive_enrolled(folder_structure, parent_folder_id=None, base_path=""):
                """Recursively create course folders and add files for enrolled users"""
                created_folders = {}
                total_files = 0
                
                # Create subfolders first
                for folder_info in folder_structure['folders']:
                    folder_path = f"{base_path}/{folder_info['name']}" if base_path else folder_info['name']
                    
                    # Create course folder
                    course_subfolder = CourseContentFolder(
                        course_id=course.id,
                        title=folder_info['name'],
                        description=f'Imported from Google Drive: {folder_path}',
                        order=CourseContentFolder.query.filter_by(course_id=course.id).count() + 1,
                        parent_folder_id=parent_folder_id
                    )
                    db.session.add(course_subfolder)
                    db.session.flush()
                    
                    created_folders[folder_path] = course_subfolder.id
                    
                    # Recursively process subfolder contents
                    sub_files = create_course_folders_recursive_enrolled(
                        folder_info['structure'], 
                        course_subfolder.id, 
                        folder_path
                    )
                    total_files += sub_files
                
                # Add files to current folder level
                for file_data in folder_structure['files']:
                    content = CourseContent(
                        course_id=course.id,
                        title=file_data['name'],
                        description=f'Imported from Google Drive: {file_data["full_path"]}',
                        content_type='file',
                        content_data=file_data['view_link'],
                        drive_file_id=file_data['file_id'],
                        drive_view_link=file_data['view_link'],
                        order=CourseContent.query.filter_by(course_id=course.id).count() + 1,
                        folder_id=parent_folder_id,
                        is_published=request.form.get('import_published') == 'on',
                        allow_others_to_view=True,
                        is_imported=True
                    )
                    db.session.add(content)
                    total_files += 1
                
                return total_files
            
            # Create the root course folder
            course_folder = CourseContentFolder(
                course_id=course.id,
                title=folder_data['folder_name'],
                description='Imported from Google Drive folder',
                order=CourseContentFolder.query.filter_by(course_id=course.id).count() + 1
            )
            db.session.add(course_folder)
            db.session.flush()
            
            current_app.logger.debug(f"Created root course folder: {course_folder.title}, id: {course_folder.id}")
            
            # Reconstruct folder structure from flat file list
            folder_structure = {'folders': [], 'files': []}
            folder_map = {}
            
            # Group files by their folder paths
            for file_data in folder_data['files']:
                folder_path = file_data.get('folder_path', '')
                
                if folder_path:
                    # This file is in a subfolder
                    if folder_path not in folder_map:
                        folder_map[folder_path] = {'folders': [], 'files': []}
                    folder_map[folder_path]['files'].append(file_data)
                else:
                    # This file is in the root folder
                    folder_structure['files'].append(file_data)
            
            # Add files to appropriate folders
            imported_count = 0
            
            # Add root level files
            for file_data in folder_data['files']:
                folder_path = file_data.get('folder_path', '')
                
                if not folder_path:
                    # Root level file
                    content = CourseContent(
                        course_id=course.id,
                        title=file_data['name'],
                        description=f'Imported from Google Drive: {file_data.get("full_path", file_data["name"])}',
                        content_type='file',
                        content_data=file_data['view_link'],
                        drive_file_id=file_data['file_id'],
                        drive_view_link=file_data['view_link'],
                        order=imported_count + 1,
                        folder_id=course_folder.id,
                        is_published=request.form.get('import_published') == 'on',
                        allow_others_to_view=True,
                        is_imported=True
                    )
                    db.session.add(content)
                    imported_count += 1
            
            # For subfolders, create them and add their files
            subfolder_files = [f for f in folder_data['files'] if f.get('folder_path')]
            if subfolder_files:
                # Group by immediate parent folder
                folder_groups = {}
                for file_data in subfolder_files:
                    folder_path = file_data.get('folder_path', '')
                    if folder_path:
                        parent_folder = folder_path.split('/')[0]  # Get immediate parent
                        if parent_folder not in folder_groups:
                            folder_groups[parent_folder] = []
                        folder_groups[parent_folder].append(file_data)
                
                # Create subfolders and add files
                for subfolder_name, files in folder_groups.items():
                    subfolder = CourseContentFolder(
                        course_id=course.id,
                        title=subfolder_name,
                        description='Subfolder imported from Google Drive',
                        order=CourseContentFolder.query.filter_by(course_id=course.id).count() + 1,
                        parent_folder_id=course_folder.id
                    )
                    db.session.add(subfolder)
                    db.session.flush()
                    
                    for file_data in files:
                        content = CourseContent(
                            course_id=course.id,
                            title=file_data['name'],
                            description=f'Imported from Google Drive: {file_data.get("full_path", file_data["name"])}',
                            content_type='file',
                            content_data=file_data['view_link'],
                            drive_file_id=file_data['file_id'],
                            drive_view_link=file_data['view_link'],
                            order=imported_count + 1,
                            folder_id=subfolder.id,
                            is_published=request.form.get('import_published') == 'on',
                            allow_others_to_view=True
                        )
                        db.session.add(content)
                        imported_count += 1
            
            current_app.logger.debug(f"Added {imported_count} content items to session")
            db.session.commit()
            current_app.logger.debug("Committed recursive folder import to database")
            flash(f'Successfully imported folder "{folder_data["folder_name"]}" with {imported_count} files from all subfolders!', 'success')
            
        elif action == 'add_assignment':
            due_date_str = request.form.get('assignment_due_date')
            due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M') if due_date_str else None
            
            assignment = CourseAssignment(
                course_id=course.id,
                title=request.form.get('assignment_title', ''),
                description=request.form.get('assignment_description', ''),
                due_date=due_date,
                points=int(request.form.get('assignment_points', 100)),
                is_published=request.form.get('assignment_published') == 'on'
            )
            db.session.add(assignment)
            db.session.commit()
            flash('Assignment added successfully!', 'success')
            
        elif action == 'add_announcement':
            announcement = CourseAnnouncement(
                course_id=course.id,
                title=request.form.get('announcement_title', ''),
                message=request.form.get('announcement_message', ''),
                author_id=current_user.id,
                is_published=request.form.get('announcement_published') == 'on'
            )
            db.session.add(announcement)
            db.session.commit()
            flash('Announcement added successfully!', 'success')

        elif action == 'add_folder':
            folder_title = request.form.get('folder_title')
            folder_description = request.form.get('folder_description')
            # Log folder creation attempt with provided values
            try:
                current_app.logger.info('Add folder attempt for course_id=%s by user=%s title=%s', course.id, getattr(current_user, 'id', None), folder_title)
            except Exception:
                current_app.logger.debug(f"Add folder attempt: course={course.id} user={getattr(current_user, 'id', None)} title={folder_title}")

            if folder_title:
                from lms.models import CourseContentFolder
                folder = CourseContentFolder(
                    course_id=course.id,
                    title=folder_title,
                    description=folder_description or '',
                    order=course.content_folders.count() + 1
                )
                db.session.add(folder)
                # Log DB URI for debugging (resolve sqlite path if used)
                try:
                    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
                    if db_uri and db_uri.startswith('sqlite:///'):
                        sqlite_path = db_uri.replace('sqlite:///', '')
                        sqlite_path = os.path.abspath(sqlite_path)
                        current_app.logger.info('Using SQLite DB at %s', sqlite_path)
                    else:
                        current_app.logger.info('Using DB URI: %s', db_uri)
                except Exception:
                    current_app.logger.debug("DB URI debug failed")

                db.session.commit()

                # Verify persistence immediately after commit
                try:
                    from lms.models import CourseContentFolder as CCF
                    reloaded = CCF.query.get(folder.id)
                    count = CCF.query.filter_by(course_id=course.id).count()
                    current_app.logger.info('Folder created id=%s title=%s reloaded=%s course_folder_count=%s', folder.id, folder.title, bool(reloaded), count)
                except Exception as e:
                    current_app.logger.exception('Post-commit verification failed: %s', e)

                flash('Folder added successfully!', 'success')
            else:
                flash('Folder title is required.', 'error')
            
        elif action == 'move_content':
            content_id = request.form.get('content_id')
            target_folder_id = request.form.get('target_folder_id')
            content = CourseContent.query.get(content_id)
            if content and content.course_id == course.id:
                content.folder_id = int(target_folder_id) if target_folder_id else None
                db.session.commit()
                flash('Content moved successfully!', 'success')
            else:
                flash('Content not found or permission denied.', 'error')
        
        elif action == 'bulk_delete_content' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            from lms.google_drive_service import authenticate, delete_file
            
            content_ids = request.form.getlist('content_ids')
            deleted_count = 0
            
            for content_id in content_ids:
                content = CourseContent.query.get(content_id)
                if content and content.course_id == course.id:
                    # Delete from Google Drive only if the app uploaded it
                    if content.drive_file_id and not content.is_imported:
                        service = authenticate()
                        if service:
                            try:
                                delete_file(service, content.drive_file_id)
                            except Exception as e:
                                current_app.logger.error(f"Error deleting file from Google Drive: {e}")
                    
                    # Delete from database
                    db.session.delete(content)
                    deleted_count += 1
            
            db.session.commit()
            flash(f'{deleted_count} items deleted successfully!', 'success')
        
        elif action == 'bulk_move_content' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            
            selected_ids = request.form.get('selected_ids', '')
            if not selected_ids:
                flash('No items selected for moving.', 'warning')
                return redirect(request.referrer or url_for('main.index'))
            
            content_ids = selected_ids.split(',')
            target_folder_id = request.form.get('target_folder_id')
            moved_count = 0
            
            for content_id in content_ids:
                content_id = content_id.strip()
                if not content_id or not content_id.isdigit():
                    continue
                content = CourseContent.query.get(int(content_id))
                if content and content.course_id == course.id:
                    content.folder_id = int(target_folder_id) if target_folder_id else None
                    moved_count += 1
            
            db.session.commit()
            flash(f'{moved_count} items moved successfully!', 'success')
        
        elif action == 'bulk_toggle_visibility' and (current_user.is_teacher or current_user.is_admin):
            from lms.models import CourseContent
            
            content_ids = request.form.getlist('content_ids')
            toggled_count = 0
            
            for content_id in content_ids:
                content = CourseContent.query.get(content_id)
                if content and content.course_id == course.id:
                    content.is_published = not content.is_published
                    toggled_count += 1
            
            db.session.commit()
            flash(f'Visibility toggled for {toggled_count} items!', 'success')
        
        elif action == 'grade_submission' and (current_user.is_admin):
            from lms.models import CourseAssignmentSubmission
            submission_id = request.form.get('submission_id')
            grade = request.form.get('grade')
            comment = request.form.get('comment')
            passed_flag = request.form.get('passed') == 'on'
            
            submission = CourseAssignmentSubmission.query.get(submission_id)
            if submission:
                if grade:
                    submission.grade = int(grade)
                if comment:
                    submission.comment = comment
                submission.passed = passed_flag
                db.session.commit()
                flash('Grade and comment saved successfully!', 'success')
        
        elif action == 'decline_submission' and (current_user.is_admin):
            from lms.models import CourseAssignmentSubmission
            submission_id = request.form.get('submission_id')

            submission = CourseAssignmentSubmission.query.get(submission_id)
            if submission:
                # Toggle declined status
                submission.declined = not submission.declined
                db.session.commit()
                if submission.declined:
                    flash('Submission declined successfully!', 'success')
                else:
                    flash('Declined status cleared!', 'success')

        return redirect(request.url, code=303)
    
    # Get all course data
    contents = CourseContent.query.filter_by(course_id=course.id).order_by(CourseContent.order).all()
    assignments = CourseAssignment.query.filter_by(course_id=course.id).order_by(CourseAssignment.due_date).all()
    announcements = CourseAnnouncement.query.filter_by(course_id=course.id).order_by(CourseAnnouncement.created_at.desc()).all()
    
    return render_template('course_editor.html', 
                         course=course, 
                         slug=slug,
                         contents=contents,
                         assignments=assignments,
                         announcements=announcements)

@main_bp.route('/course/<slug>/messages')
@login_required
def view_course_messages(slug):
    from lms.models import Course, CourseAnnouncement, CourseAnnouncementReply
    from slugify import slugify
    # Only allow admin/teacher
    if not current_user.is_admin:
        flash('You do not have permission to view messages.', 'error')
        return redirect(url_for('main.index'))
    # Find course by slug
    courses = Course.query.all()
    course = None
    for c in courses:
        if slugify(c.title) == slug:
            course = c
            break
    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('main.index'))
    # Get all announcements and their replies
    announcements = CourseAnnouncement.query.filter_by(course_id=course.id).order_by(CourseAnnouncement.created_at.desc()).all()
    return render_template('course_forum.html', course=course, announcements=announcements, CourseAnnouncementReply=CourseAnnouncementReply)

@main_bp.route('/move_file', methods=['POST'])
def move_file():
    from lms.models import CourseContent, db

    # Get form data
    file_id = request.form.get('file_id')
    new_folder_id = request.form.get('new_folder_id')

    # Find the file
    file = CourseContent.query.get(file_id)
    if not file:
        flash('File not found.', 'error')
        return redirect(request.referrer or url_for('main.index'))

    # Update the folder_id
    file.folder_id = new_folder_id if new_folder_id else None
    db.session.commit()

    flash('File moved successfully!', 'success')
    return redirect(request.referrer or url_for('main.index'))

@main_bp.route('/move_folder', methods=['POST'])
def move_folder():
    from lms.models import CourseContentFolder, db

    # Get form data
    folder_id = request.form.get('folder_id')
    new_parent_folder_id = request.form.get('new_parent_folder_id')

    # Find the folder
    folder = CourseContentFolder.query.get(folder_id)
    if not folder:
        flash('Folder not found.', 'error')
        return redirect(request.referrer or url_for('main.index'))

    # Prevent moving a folder into itself or any of its descendants
    if new_parent_folder_id and (
        str(folder_id) == str(new_parent_folder_id)
        or _folder_is_ancestor_of(int(folder_id), int(new_parent_folder_id))
    ):
        flash('Cannot move a folder into itself or one of its subfolders.', 'error')
        return redirect(request.referrer or url_for('main.index'))

    # Update the parent_folder_id
    folder.parent_folder_id = int(new_parent_folder_id) if new_parent_folder_id else None
    db.session.commit()

    flash('Folder moved successfully!', 'success')
    return redirect(request.referrer or url_for('main.index'))


@main_bp.route('/set_language/<lang>')
def set_language(lang):
    """Set the language for the current session"""
    from flask import session, redirect, request

    current_app.logger.debug(f"Attempting to set language to: {lang}")
    current_app.logger.debug(f"Session before: {dict(session)}")
    
    if lang in ['en', 'ru', 'az']:
        session['language'] = lang
        session.modified = True
        session.permanent = True
        current_app.logger.debug(f"Language set to: {lang}")
        current_app.logger.debug(f"Session after: {dict(session)}")
    else:
        current_app.logger.debug(f"Invalid language: {lang}")
    
    # Redirect back to the referring page or home
    redirect_url = request.referrer or url_for('main.index')
    current_app.logger.debug(f"Redirecting to: {redirect_url}")
    return redirect(redirect_url)


@main_bp.route('/debug/locale')
def debug_locale():
    """Debug endpoint to check locale settings"""
    from flask import session
    from flask_babel import get_locale as babel_get_locale
    
    try:
        babel_locale = babel_get_locale()
        babel_locale_str = str(babel_locale)
        babel_locale_type = str(type(babel_locale))
    except Exception as e:
        babel_locale_str = f"Error: {e}"
        babel_locale_type = "Error"
    
    session_lang = session.get('language')
    our_locale = get_locale()
    
    result = {
        'session_language': str(session_lang) if session_lang else None,
        'session_language_type': str(type(session_lang)),
        'babel_locale': babel_locale_str,
        'babel_locale_type': babel_locale_type,
        'our_get_locale': str(our_locale) if our_locale else None,
        'our_get_locale_type': str(type(our_locale)),
    }
    return jsonify(result)


# ── Certificate download routes ───────────────────────────────────────────────

@main_bp.route('/certificate/image/<cert_id>')
def certificate_image(cert_id):
    import io
    from flask import send_file
    from lms.models import Certificate
    from lms.certificate_generator import get_cached_png_bytes
    cert = Certificate.query.get_or_404(cert_id)
    if cert.revoked:
        abort(410)
    png = get_cached_png_bytes(cert)
    return send_file(io.BytesIO(png), mimetype='image/png')


@main_bp.route('/certificate/download/<cert_id>/image')
@login_required
def download_certificate_image(cert_id):
    import io
    from flask import send_file
    from lms.models import Certificate
    from lms.certificate_generator import get_cached_png_bytes
    cert = Certificate.query.get_or_404(cert_id)
    if cert.user_id != current_user.id and not (current_user.is_admin or current_user.is_teacher):
        abort(403)
    if cert.revoked:
        abort(410)
    png = get_cached_png_bytes(cert)
    return send_file(io.BytesIO(png), mimetype='image/png', as_attachment=True,
                     download_name=f"Certificate-{cert.cert_id_display}.png")


@main_bp.route('/certificate/download/<cert_id>/pdf')
@login_required
def download_certificate_pdf(cert_id):
    import io
    from flask import send_file
    from lms.models import Certificate
    from lms.certificate_generator import get_cached_pdf_bytes
    cert = Certificate.query.get_or_404(cert_id)
    if cert.user_id != current_user.id and not (current_user.is_admin or current_user.is_teacher):
        abort(403)
    if cert.revoked:
        abort(410)
    pdf = get_cached_pdf_bytes(cert)
    return send_file(io.BytesIO(pdf), mimetype='application/pdf', as_attachment=True,
                     download_name=f"Certificate-{cert.cert_id_display}.pdf")


@main_bp.route('/certificate/<cert_id>')
def verify_certificate(cert_id):
    from lms.models import Certificate, SiteSettings
    cert = Certificate.query.get_or_404(cert_id)
    site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    if cert.revoked:
        return render_template('certificate_revoked.html', cert=cert, site_settings=site_settings), 410
    return render_template('certificate_verify.html', cert=cert, site_settings=site_settings)


# ── User profile (name fields) ────────────────────────────────────────────────

@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    from lms.models import db, SiteSettings
    site_settings = SiteSettings.query.filter_by(is_active=True).first() or SiteSettings()
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name', '').strip() or None
        current_user.last_name = request.form.get('last_name', '').strip() or None
        current_user.city = request.form.get('city', '').strip() or None
        db.session.commit()
        flash('Profile updated.')
        return redirect(url_for('main.profile'))
    return render_template('profile.html', site_settings=site_settings)


@main_bp.route('/profile/export')
@login_required
def export_my_data():
    """Self-service GDPR data export — download the current user's own data as JSON."""
    import json
    from flask import Response
    from lms.data_export import export_user_data

    data = export_user_data(current_user)
    body = json.dumps(data, indent=2)
    return Response(
        body,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename=lms_data_{current_user.username}.json'}
    )


@main_bp.route('/profile/delete', methods=['POST'])
@login_required
def delete_my_account():
    """Self-service GDPR account deletion — anonymizes the account and logs the user out."""
    from flask_login import logout_user
    from lms.models import db
    from lms.data_export import anonymize_user

    password = request.form.get('password', '')
    if not current_user.check_password(password):
        flash('Incorrect password. Account was not deleted.', 'error')
        return redirect(url_for('main.profile'))

    anonymize_user(current_user)
    db.session.commit()
    logout_user()
    flash('Your account and personal data have been deleted.')
    return redirect(url_for('main.index'))
