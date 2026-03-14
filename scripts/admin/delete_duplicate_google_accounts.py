#!/usr/bin/env python3
"""
Script to delete all accounts that have duplicate Google account links.

This script identifies users with duplicate Google OAuth tokens or emails
and deletes all accounts in each duplicate group.
"""

import os
import sys
from collections import defaultdict

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, continue

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yonca import create_app
from yonca.models import User, db

def find_duplicate_google_accounts():
    """Find all users with duplicate Google account links."""
    print("🔍 Finding duplicate Google account links...")

    # Get all users with Google OAuth tokens
    users_with_google = User.query.filter(
        User.google_access_token.isnot(None)
    ).all()

    print(f"📊 Found {len(users_with_google)} users with Google OAuth tokens")

    # Group by google_access_token
    token_groups = defaultdict(list)
    for user in users_with_google:
        token_groups[user.google_access_token].append(user)

    # Group by email (in case there are email duplicates)
    email_groups = defaultdict(list)
    for user in users_with_google:
        if user.email:
            email_groups[user.email].append(user)

    # Find duplicates
    duplicate_groups = []

    # Check token duplicates
    for token, users in token_groups.items():
        if len(users) > 1:
            duplicate_groups.append({
                'type': 'google_access_token',
                'identifier': token[:50] + '...' if len(token) > 50 else token,
                'users': users
            })

    # Check email duplicates (only if they have Google tokens)
    for email, users in email_groups.items():
        if len(users) > 1:
            # Check if this email group was already caught by token duplicates
            already_caught = any(
                any(u in group['users'] for u in users)
                for group in duplicate_groups
            )
            if not already_caught:
                duplicate_groups.append({
                    'type': 'email',
                    'identifier': email,
                    'users': users
                })

    return duplicate_groups

def delete_duplicate_accounts(duplicate_groups, dry_run=True):
    """Delete all accounts in duplicate groups."""
    total_deleted = 0

    for i, group in enumerate(duplicate_groups, 1):
        print(f"\n{'🧪 DRY RUN' if dry_run else '🗑️  DELETING'} Group {i}: {group['type']} = {group['identifier']}")
        print(f"   Users to delete: {len(group['users'])}")

        for user in group['users']:
            print(f"   - ID: {user.id}, Username: {user.username}, Email: {user.email}")

            if not dry_run:
                try:
                    db.session.delete(user)
                    total_deleted += 1
                    print(f"   ✅ Deleted user {user.username}")
                except Exception as e:
                    print(f"   ❌ Error deleting user {user.username}: {e}")

    if not dry_run:
        try:
            db.session.commit()
            print(f"\n✅ Successfully deleted {total_deleted} duplicate accounts")
        except Exception as e:
            print(f"\n❌ Error committing changes: {e}")
            db.session.rollback()

    return total_deleted

def main():
    """Main function to run the duplicate account cleanup."""
    print("🧹 Google Account Duplicate Cleanup Script")
    print("=" * 50)

    # Create Flask app context
    app = create_app()

    with app.app_context():
        # Find duplicates
        duplicate_groups = find_duplicate_google_accounts()

        if not duplicate_groups:
            print("✅ No duplicate Google account links found!")
            print("\n📊 Summary:")
            users_with_google = User.query.filter(
                User.google_access_token.isnot(None)
            ).all()
            print(f"   - Total users with Google OAuth: {len(users_with_google)}")
            for user in users_with_google:
                print(f"   - {user.username} ({user.email})")
            return

        print(f"\n🚨 Found {len(duplicate_groups)} groups of duplicate accounts")
        print(f"📈 Total accounts to delete: {sum(len(g['users']) for g in duplicate_groups)}")

        # Ask for confirmation
        if len(duplicate_groups) > 0:
            print("\n⚠️  WARNING: This will permanently delete all accounts in duplicate groups!")
            response = input("\nRun dry-run first? (y/n): ").lower().strip()

            if response == 'y':
                # Dry run
                delete_duplicate_accounts(duplicate_groups, dry_run=True)

                # Ask to proceed with actual deletion
                response = input("\nProceed with actual deletion? (y/n): ").lower().strip()
                if response == 'y':
                    delete_duplicate_accounts(duplicate_groups, dry_run=False)
                else:
                    print("❌ Operation cancelled")
            else:
                print("❌ Operation cancelled")

if __name__ == '__main__':
    main()