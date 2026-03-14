#!/usr/bin/env python3
"""
Script to reset the PostgreSQL database: drop all tables and recreate them empty.
"""

import psycopg2
import subprocess
import os
from urllib.parse import urlparse

# Get database URL from environment
database_url = os.getenv('DATABASE_URL')
if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set")
parsed = urlparse(database_url)

# Database connection details
DB_HOST = parsed.hostname or 'localhost'
try:
    DB_PORT = parsed.port or 5432
except (ValueError, TypeError):
    DB_PORT = 5432
DB_NAME = parsed.path.lstrip('/') or 'yonca_db'
DB_USER = parsed.username or 'postgres'
DB_PASSWORD = parsed.password

def reset_database():
    try:
        # First, connect to postgres database to drop and recreate yonca_db
        postgres_url = f"{parsed.scheme}://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}/postgres"
        conn = psycopg2.connect(postgres_url)
        conn.autocommit = True
        cur = conn.cursor()

        # Terminate active connections to the database
        cur.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
        """, (DB_NAME,))

        # Drop the database if it exists
        cur.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}"')

        # Create the database
        cur.execute(f'CREATE DATABASE "{DB_NAME}"')

        cur.close()
        conn.close()

        print(f"Database {DB_NAME} dropped and recreated successfully.")

        # Now create tables using SQLAlchemy
        print("Creating database tables...")
        from yonca import create_app
        from yonca.models import db
        app = create_app('production')
        with app.app_context():
            db.create_all()
        
        print("Database reset and tables created successfully.")

    except Exception as e:
        print(f"Error resetting database: {e}")

if __name__ == '__main__':
    reset_database()