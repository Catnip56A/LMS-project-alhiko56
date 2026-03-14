#!/usr/bin/env python3
"""
Script to add missing database columns and tables.
"""

from yonca import create_app

def add_missing_schema():
    app = create_app('production')
    with app.app_context():
        from yonca.models import db
        # Create missing tables
        db.create_all()
        print("Created missing tables.")

        # Add missing columns
        # For resource table, add preview_image if not exists
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE resource ADD COLUMN IF NOT EXISTS preview_image VARCHAR(300)"))
                conn.commit()
            print("Added preview_image column to resource table.")
        except Exception as e:
            print(f"Error adding column: {e}")

if __name__ == '__main__':
    add_missing_schema()