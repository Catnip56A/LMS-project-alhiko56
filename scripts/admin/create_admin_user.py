#!/usr/bin/env python3
"""
Script to create an admin user with a specified password.
Usage: python scripts/admin/create_admin_user.py [username] [email] [password]
"""
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lms import create_app
from lms.models import db, User


def create_admin_user(username='admin', email='admin@lms.local', password='lms2026'):
    """Create an admin user in the database."""
    
    app = create_app()
    
    with app.app_context():
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"❌ User '{username}' already exists!")
            return False
        
        # Create new admin user
        user = User(
            username=username,
            email=email,
            is_admin=True,
            is_teacher=True,
            preferred_language='en'
        )
        user.password = password
        
        # Add to database
        db.session.add(user)
        db.session.commit()
        
        print(f"✅ Admin user created successfully!")
        print(f"   Username: {username}")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Admin: Yes")
        print(f"   Teacher: Yes")
        return True


if __name__ == '__main__':
    # Parse command line arguments
    username = sys.argv[1] if len(sys.argv) > 1 else 'admin'
    email = sys.argv[2] if len(sys.argv) > 2 else 'admin@lms.local'
    password = sys.argv[3] if len(sys.argv) > 3 else 'lms2026'
    
    print(f"Creating admin user with username '{username}'...")
    success = create_admin_user(username, email, password)
    
    sys.exit(0 if success else 1)
