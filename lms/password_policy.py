"""
Password strength rules shared between self-service change-password and admin user
management. No Flask/DB dependency.
"""
import re

MIN_LENGTH = 8


class PasswordPolicyError(ValueError):
    """Raised when a password doesn't meet the minimum strength bar."""


def validate_password_strength(password):
    """Raise PasswordPolicyError with a user-facing message if the password is too weak."""
    if len(password) < MIN_LENGTH:
        raise PasswordPolicyError(f'Password must be at least {MIN_LENGTH} characters long.')

    classes_present = sum([
        bool(re.search(r'[a-z]', password)),
        bool(re.search(r'[A-Z]', password)),
        bool(re.search(r'\d', password)),
        bool(re.search(r'[^a-zA-Z0-9]', password)),
    ])
    if classes_present < 3:
        raise PasswordPolicyError(
            'Password must include at least 3 of: lowercase letters, uppercase letters, numbers, symbols.'
        )
