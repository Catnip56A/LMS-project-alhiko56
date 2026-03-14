#!/usr/bin/env python3
"""
Script to fix drive_view_link fields that point to API endpoints instead of Google Drive.

This fixes redirect loops where drive_view_link points to /api/file/ instead of direct Google Drive URLs.
"""

import os
import sys
import re

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yonca import create_app
from yonca.models import CourseAssignmentSubmission, CourseContent, Resource, PDFDocument, db

def fix_api_endpoint_links():
    """Fix drive_view_link fields that point to API endpoints instead of Google Drive."""
    print("🔧 Fixing drive_view_link fields that point to API endpoints...")

    # Create Flask app context
    app = create_app()

    with app.app_context():
        fixed_count = 0

        # Pattern to match API endpoint links: /api/file/<file_id>
        api_pattern = re.compile(r'.*/api/file/([a-zA-Z0-9_-]+)')

        # Fix CourseAssignmentSubmission
        submissions = CourseAssignmentSubmission.query.filter(
            CourseAssignmentSubmission.drive_view_link.like('%/api/file/%')
        ).all()

        for submission in submissions:
            match = api_pattern.match(submission.drive_view_link)
            if match:
                file_id = match.group(1)
                new_link = f'https://drive.google.com/file/d/{file_id}/view'
                print(f"🔄 Fixing CourseAssignmentSubmission ID {submission.id}")
                print(f"   Old: {submission.drive_view_link}")
                print(f"   New: {new_link}")
                submission.drive_view_link = new_link
                fixed_count += 1

        # Fix CourseContent
        contents = CourseContent.query.filter(
            CourseContent.drive_view_link.like('%/api/file/%')
        ).all()

        for content in contents:
            match = api_pattern.match(content.drive_view_link)
            if match:
                file_id = match.group(1)
                new_link = f'https://drive.google.com/file/d/{file_id}/view'
                print(f"🔄 Fixing CourseContent ID {content.id}")
                print(f"   Old: {content.drive_view_link}")
                print(f"   New: {new_link}")
                content.drive_view_link = new_link
                fixed_count += 1

        # Fix Resource preview_image (if it exists and has API links)
        if hasattr(Resource, 'preview_image'):
            resources = Resource.query.filter(
                Resource.preview_image.like('%/api/file/%')
            ).all()

            for resource in resources:
                match = api_pattern.match(resource.preview_image)
                if match:
                    file_id = match.group(1)
                    new_link = f'https://drive.google.com/file/d/{file_id}/view'
                    print(f"🔄 Fixing Resource ID {resource.id} preview_image")
                    print(f"   Old: {resource.preview_image}")
                    print(f"   New: {new_link}")
                    resource.preview_image = new_link
                    fixed_count += 1

        # Commit all changes
        if fixed_count > 0:
            try:
                db.session.commit()
                print(f"\n✅ Successfully fixed {fixed_count} problematic links!")
                print("These links now point directly to Google Drive instead of API endpoints.")
            except Exception as e:
                print(f"\n❌ Error committing changes: {e}")
                db.session.rollback()
        else:
            print("\n✅ No problematic links found to fix!")

def main():
    """Main function to run the link fixing script."""
    print("🔧 Drive View Link Fix Script")
    print("=" * 40)
    print("This script fixes drive_view_link fields that point to /api/file/ endpoints")
    print("instead of direct Google Drive URLs, which causes redirect loops.")
    print()

    fix_api_endpoint_links()

if __name__ == '__main__':
    main()