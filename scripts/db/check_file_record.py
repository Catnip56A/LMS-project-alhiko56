#!/usr/bin/env python3
"""
Script to check file records and their drive_view_links
"""

import os
import sys

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yonca import create_app
from yonca.models import CourseAssignmentSubmission, CourseContent, Resource, PDFDocument

def check_file_record(file_id):
    """Check what file record corresponds to the given file ID"""
    print(f"🔍 Checking file ID: {file_id}")

    # Create Flask app context
    app = create_app()

    with app.app_context():
        # Find the file in any of the models that store files
        submission = CourseAssignmentSubmission.query.filter_by(drive_file_id=file_id).first()
        course_content = CourseContent.query.filter_by(drive_file_id=file_id).first()
        resource = Resource.query.filter_by(drive_file_id=file_id).first()
        pdf_doc = PDFDocument.query.filter_by(drive_file_id=file_id).first()

        file_record = submission or course_content or resource or pdf_doc

        if file_record:
            print(f"✅ Found file record: {type(file_record).__name__}")
            print(f"   ID: {file_record.id}")

            if hasattr(file_record, 'drive_view_link'):
                link = file_record.drive_view_link
                print(f"   drive_view_link: {link}")
                if link and '/api/file/' in link:
                    print("   ⚠️  WARNING: drive_view_link points to API endpoint (redirect loop!)")
                elif link and 'drive.google.com' in link:
                    print("   ✅ drive_view_link points to Google Drive")
                else:
                    print("   ❓ drive_view_link format unknown")

            if hasattr(file_record, 'allow_others_to_view'):
                print(f"   allow_others_to_view: {file_record.allow_others_to_view}")

            if hasattr(file_record, 'user_id'):
                print(f"   user_id: {file_record.user_id}")

            if hasattr(file_record, 'title'):
                print(f"   title: {file_record.title}")

        else:
            print("❌ File not found in database")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        file_id = sys.argv[1]
    else:
        # Use the file ID from the logs
        file_id = '1DHbetyIQAijs4xHLAwkQHKtH-gL1tDmO'

    check_file_record(file_id)