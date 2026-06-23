#!/usr/bin/env python3
"""
Promote an existing user to full admin (is_admin=True).

Usage:
  python scripts/admin/make_full_admin.py <username>

Via Docker (dev):
  docker compose --profile dev run --rm -e DATABASE_URL=... app-dev \
    python scripts/admin/make_full_admin.py <username>

Or via just:
  just make-admin <username>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from yonca import create_app
from yonca.models import db, User


def make_full_admin(username: str) -> bool:
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"Error: user '{username}' not found.")
            return False

        if user.is_admin:
            print(f"'{username}' is already a full admin.")
            return True

        user.is_admin = True
        user.admin_permissions = None  # full admins don't need permission entries
        db.session.commit()

        print(f"Done: '{username}' is now a full admin.")
        return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <username>")
        sys.exit(1)

    sys.exit(0 if make_full_admin(sys.argv[1]) else 1)
