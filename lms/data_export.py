"""
GDPR-adjacent self-service helpers: export a user's own data as a plain dict (JSON-ready),
and anonymize a user's account on deletion.

Account "deletion" anonymizes the User row rather than removing it outright — several
tables (forum messages, assignment submissions, reviews, certificates) have NOT NULL
foreign keys to `user.id`, so a hard delete would either orphan that content or require a
much larger cascade-delete migration. Anonymizing in place (clearing PII, invalidating
login) satisfies the erasure request without breaking referential integrity or other
users' content (e.g. a forum thread a deleted user posted in).
"""
import secrets
from datetime import datetime


def export_user_data(user):
    """Return the given user's own data as a JSON-serializable dict."""
    from lms.models import ForumMessage, CourseAssignmentSubmission, CourseReview, Certificate

    def iso(dt):
        return dt.isoformat() if dt else None

    return {
        'profile': {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'city': user.city,
            'is_admin': user.is_admin,
            'created_at': iso(user.created_at),
        },
        'enrolled_courses': [
            {'id': e.course.id, 'title': e.course.title, 'is_teacher': e.is_teacher, 'created_by_me': e.course.created_by == user.id}
            for e in user.enrollments
        ],
        # Covers every message type — global channel, course channel (formerly
        # CourseAnnouncement/CourseAnnouncementReply, now unified here), Group, and DM.
        'forum_messages': [
            {'id': m.id, 'channel': m.forum_channel.slug, 'message': m.message, 'timestamp': iso(m.timestamp)}
            for m in ForumMessage.query.filter_by(user_id=user.id).all()
        ],
        'assignment_submissions': [
            {
                'id': s.id, 'assignment_id': s.assignment_id, 'submitted_at': iso(s.submitted_at),
                'grade': s.grade, 'passed': s.passed,
            }
            for s in CourseAssignmentSubmission.query.filter_by(user_id=user.id).all()
        ],
        'course_reviews': [
            {'id': r.id, 'course_id': r.course_id, 'rating': r.rating, 'title': r.title, 'review_text': r.review_text}
            for r in CourseReview.query.filter_by(user_id=user.id).all()
        ],
        'certificates': [
            {'id': c.id, 'course_id': c.course_id, 'issued_at': iso(c.issued_at), 'revoked': c.revoked}
            for c in Certificate.query.filter_by(user_id=user.id).all()
        ],
    }


def anonymize_user(user):
    """Scrub personal data from a user's account in place. Caller is responsible for commit + logout."""
    user.username = f'deleted_user_{user.id}'
    user.email = None
    user.first_name = None
    user.last_name = None
    user.city = None
    user.password = secrets.token_urlsafe(32)  # unusable random password
    user.google_access_token = None
    user.google_refresh_token = None
    user.google_token_expiry = None
    user.email_verified = False
    user.last_attempt_time = datetime.utcnow()
