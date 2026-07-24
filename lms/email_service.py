"""
Email verification tokens + sending. No Flask app-context dependency beyond the secret key
and app.logger being passed in explicitly, so this stays easy to test.

Sending is dev-mode only for now: the link is logged rather than actually emailed. Swap
send_verification_email's body for a real provider (SMTP/SES/etc.) when one is configured —
call sites don't need to change.
"""
import logging
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

SALT = 'email-verify'
DEFAULT_MAX_AGE = 60 * 60 * 24  # 24 hours

logger = logging.getLogger(__name__)


def generate_verification_token(secret_key, email):
    return URLSafeTimedSerializer(secret_key).dumps(email, salt=SALT)


def confirm_verification_token(secret_key, token, max_age=DEFAULT_MAX_AGE):
    """Return the email the token was issued for, or None if invalid/expired."""
    try:
        return URLSafeTimedSerializer(secret_key).loads(token, salt=SALT, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def send_verification_email(email, verification_url):
    logger.info(f"[dev-mode email] Verification link for {email}: {verification_url}")
