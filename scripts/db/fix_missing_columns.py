#!/usr/bin/env python3
"""
Script to manually add missing allow_others_to_view columns to production database.

This script adds the missing database columns that were added in migrations
but haven't been applied to the production PostgreSQL database.
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
from yonca.models import db
import sqlalchemy as sa

def add_missing_columns():
    """Add missing allow_others_to_view columns to database tables."""
    print("🔧 Adding missing allow_others_to_view columns to production database...")

    # Get database engine
    engine = db.engine

    # Check which tables are missing the column
    tables_to_check = [
        'course_content',
        'course_assignment_submission',
        'resource',
        'pdf_document'
    ]

    missing_columns = {}

    with engine.connect() as conn:
        for table_name in tables_to_check:
            try:
                # Check if column exists
                result = conn.execute(sa.text(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                    AND column_name = 'allow_others_to_view'
                """))

                if not result.fetchone():
                    missing_columns[table_name] = True
                    print(f"❌ Missing allow_others_to_view column in {table_name}")
                else:
                    print(f"✅ Column exists in {table_name}")

            except Exception as e:
                print(f"⚠️  Error checking {table_name}: {e}")

    if not missing_columns:
        print("✅ All required columns already exist!")
        return

    print(f"\n📋 Will add allow_others_to_view column to: {list(missing_columns.keys())}")

    # Add the missing columns
    try:
        with engine.connect() as conn:
            # Add to course_content
            if 'course_content' in missing_columns:
                print("➕ Adding allow_others_to_view to course_content...")
                conn.execute(sa.text("""
                    ALTER TABLE course_content
                    ADD COLUMN allow_others_to_view BOOLEAN DEFAULT TRUE
                """))
                conn.commit()
                print("✅ Added to course_content")

            # Add to course_assignment_submission
            if 'course_assignment_submission' in missing_columns:
                print("➕ Adding allow_others_to_view to course_assignment_submission...")
                conn.execute(sa.text("""
                    ALTER TABLE course_assignment_submission
                    ADD COLUMN allow_others_to_view BOOLEAN DEFAULT FALSE
                """))
                conn.commit()
                print("✅ Added to course_assignment_submission")

            # Add to resource
            if 'resource' in missing_columns:
                print("➕ Adding allow_others_to_view to resource...")
                conn.execute(sa.text("""
                    ALTER TABLE resource
                    ADD COLUMN allow_others_to_view BOOLEAN DEFAULT TRUE
                """))
                conn.commit()
                print("✅ Added to resource")

            # Add to pdf_document
            if 'pdf_document' in missing_columns:
                print("➕ Adding allow_others_to_view to pdf_document...")
                conn.execute(sa.text("""
                    ALTER TABLE pdf_document
                    ADD COLUMN allow_others_to_view BOOLEAN DEFAULT TRUE
                """))
                conn.commit()
                print("✅ Added to pdf_document")

        print("\n🎉 Successfully added all missing columns!")

    except Exception as e:
        print(f"\n❌ Error adding columns: {e}")
        print("You may need to run these SQL commands manually in your PostgreSQL database:")
        print()
        if 'course_content' in missing_columns:
            print("ALTER TABLE course_content ADD COLUMN allow_others_to_view BOOLEAN DEFAULT TRUE;")
        if 'course_assignment_submission' in missing_columns:
            print("ALTER TABLE course_assignment_submission ADD COLUMN allow_others_to_view BOOLEAN DEFAULT FALSE;")
        if 'resource' in missing_columns:
            print("ALTER TABLE resource ADD COLUMN allow_others_to_view BOOLEAN DEFAULT TRUE;")
        if 'pdf_document' in missing_columns:
            print("ALTER TABLE pdf_document ADD COLUMN allow_others_to_view BOOLEAN DEFAULT TRUE;")

def main():
    """Main function to run the column addition script."""
    print("🔧 Production Database Column Fix Script")
    print("=" * 50)

    # Create Flask app context
    app = create_app()

    with app.app_context():
        add_missing_columns()

if __name__ == '__main__':
    main()