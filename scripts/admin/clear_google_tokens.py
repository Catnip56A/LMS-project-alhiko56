"""Script to clear Google OAuth tokens so users need to re-authorize with new scopes"""
from yonca import create_app
app = create_app()
from yonca.models import User, db

with app.app_context():
    # Clear Google OAuth tokens for all users
    users_with_tokens = User.query.filter(
        (User.google_access_token.isnot(None)) |
        (User.google_refresh_token.isnot(None))
    ).all()

    cleared_count = 0
    for user in users_with_tokens:
        user.google_access_token = None
        user.google_refresh_token = None
        user.google_token_expiry = None
        cleared_count += 1

    db.session.commit()
    print(f"✓ Cleared Google OAuth tokens for {cleared_count} users")
    print("Users will need to re-link their Google accounts with the new Drive permissions.")