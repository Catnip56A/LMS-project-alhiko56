#!/usr/bin/env python3
"""
Script to clear email addresses from user accounts
This allows users to relink Google accounts without "already linked" errors
"""

import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from yonca import create_app
from yonca.models import db, User

def clear_user_emails():
    """Clear email addresses from user accounts"""

    app = create_app()

    with app.app_context():
        if len(sys.argv) > 1:
            # Clear email for specific user
            identifier = sys.argv[1]

            # Try to find user by username
            user = User.query.filter_by(username=identifier).first()

            if not user:
                print(f"User '{identifier}' not found")
                return

            print(f"Clearing email for user: {user.username}")
            print(f"Current email: {user.email}")

            # Clear email field
            user.email = None
            db.session.commit()
            print("✅ Email cleared successfully!")

        else:
            # Show all users with emails
            print("Users with email addresses:")
            print("-" * 50)

            users_with_emails = User.query.filter(
                User.email.isnot(None)
            ).all()

            if not users_with_emails:
                print("No users have email addresses set.")
                return

            for i, user in enumerate(users_with_emails, 1):
                print(f"{i}. Username: {user.username}")
                print(f"   Email: {user.email}")
                print()

            print("To clear email for a specific user, run:")
            print("python clear_user_emails.py <username>")

def clear_all_emails():
    """Clear emails from ALL users (dangerous!)"""

    app = create_app()

    with app.app_context():
        confirm = input("⚠️  WARNING: This will clear email addresses from ALL users! Continue? (type 'yes'): ")
        if confirm.lower() != 'yes':
            print("Operation cancelled.")
            return

        users_with_emails = User.query.filter(
            User.email.isnot(None)
        ).all()

        count = 0
        for user in users_with_emails:
            user.email = None
            count += 1

        db.session.commit()
        print(f"✅ Cleared email addresses from {count} users.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        clear_all_emails()
    else:
        clear_user_emails()