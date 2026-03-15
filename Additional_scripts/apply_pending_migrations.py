#!/usr/bin/env python3
"""
Script to apply all pending database schema changes from cyclic migrations.
Adds missing columns without relying on the broken migration chain.
"""

import os
import sys
from sqlalchemy import inspect, text

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yonca import create_app
from yonca.models import db


def add_column_if_missing(table_name, column_name, column_type, default=None):
    """Add a column to a table if it doesn't already exist."""
    try:
        inspector = inspect(db.engine)
        columns = [c["name"] for c in inspector.get_columns(table_name)]
        
        if column_name in columns:
            print(f"  ✓ {table_name}.{column_name} already exists")
            return True
        
        default_clause = f" DEFAULT {default}" if default else ""
        sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}{default_clause}'
        
        with db.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        
        print(f"  ✓ Added {table_name}.{column_name}")
        return True
    except Exception as e:
        print(f"  ✗ Error adding {table_name}.{column_name}: {e}")
        return False


def alter_column_nullable(table_name, column_name):
    """Make a column nullable."""
    try:
        inspector = inspect(db.engine)
        columns = {c["name"]: c for c in inspector.get_columns(table_name)}
        
        if column_name not in columns:
            print(f"  ✗ {table_name}.{column_name} does not exist")
            return False
        
        col = columns[column_name]
        if col["nullable"]:
            print(f"  ✓ {table_name}.{column_name} already nullable")
            return True
        
        sql = f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP NOT NULL'
        
        with db.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        
        print(f"  ✓ Made {table_name}.{column_name} nullable")
        return True
    except Exception as e:
        print(f"  ✗ Error altering {table_name}.{column_name}: {e}")
        return False


def apply_pending_migrations():
    """Apply all pending schema changes."""
    app = create_app('production')
    
    with app.app_context():
        print("🔧 Applying pending database schema changes...")
        print()
        
        # User table columns
        print("→ User table:")
        add_column_if_missing("user", "login_attempts", "INTEGER")
        add_column_if_missing("user", "last_attempt_time", "TIMESTAMP")
        add_column_if_missing("user", "google_access_token", "TEXT")
        add_column_if_missing("user", "google_refresh_token", "TEXT")
        add_column_if_missing("user", "google_token_expiry", "TIMESTAMP")
        alter_column_nullable("user", "email")
        print()
        
        # Resource table columns
        print("→ Resource table:")
        add_column_if_missing("resource", "tags", "VARCHAR(500)")
        add_column_if_missing("resource", "is_image_file", "BOOLEAN")
        add_column_if_missing("resource", "preview_drive_file_id", "VARCHAR(100)")
        add_column_if_missing("resource", "preview_drive_view_link", "VARCHAR(300)")
        alter_column_nullable("resource", "access_pin")
        alter_column_nullable("resource", "pin_expires_at")
        print()
        
        # PDF Document table columns
        print("→ PDF Document table:")
        add_column_if_missing("pdf_document", "drive_file_id", "VARCHAR(100)")
        add_column_if_missing("pdf_document", "drive_view_link", "VARCHAR(300)")
        print()
        
        # Home Content table columns
        print("→ Home Content table:")
        add_column_if_missing("home_content", "features_title", "VARCHAR(200)")
        add_column_if_missing("home_content", "features_subtitle", "VARCHAR(500)")
        print()
        
        # Course table columns
        print("→ Course table:")
        add_column_if_missing("course", "tab_content_label", "VARCHAR(50)")
        add_column_if_missing("course", "tab_assignments_label", "VARCHAR(50)")
        add_column_if_missing("course", "tab_announcements_label", "VARCHAR(50)")
        add_column_if_missing("course", "tab_reviews_label", "VARCHAR(50)")
        print()
        
        # Course Assignment Submission table columns
        print("→ Course Assignment Submission table:")
        add_column_if_missing("course_assignment_submission", "allow_others_to_view", "BOOLEAN", "FALSE")
        add_column_if_missing("course_assignment_submission", "grade", "VARCHAR(10)")
        add_column_if_missing("course_assignment_submission", "comment", "TEXT")
        print()
        
        # Course Content table columns  
        print("→ Course Content table:")
        add_column_if_missing("course_content", "allow_others_to_view", "BOOLEAN", "TRUE")
        print()
        
        print("✅ Schema update complete!")


if __name__ == '__main__':
    try:
        apply_pending_migrations()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
