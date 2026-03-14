#!/usr/bin/env python3
"""
Script to update permissions for existing Google Drive files in the Resource model
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from yonca import create_app
from yonca.models import Resource, User, db
from yonca.google_drive_service import authenticate, set_file_permissions

def update_resource_permissions():
    """Update permissions for all active resources"""
    app = create_app()

    with app.app_context():
        # Get admin user with Google tokens
        admin_user = User.query.filter_by(is_admin=True).first()
        if not admin_user:
            print("No admin user found")
            return

        if not admin_user.google_access_token:
            print("Admin user has no Google access token")
            return

        # Authenticate with Google Drive
        service = authenticate()
        if not service:
            print("Failed to authenticate with Google Drive")
            return

        # Get all active resources
        resources = Resource.query.filter_by(is_active=True).all()
        updated_count = 0

        for resource in resources:
            try:
                # Update main file permissions if allow_others_to_view is True
                if resource.allow_others_to_view and resource.drive_file_id:
                    print(f"Updating permissions for resource: {resource.title}")
                    set_file_permissions(service, resource.drive_file_id, make_public=True)
                    updated_count += 1

                # Update preview image permissions if exists
                if resource.allow_others_to_view and resource.preview_drive_file_id:
                    print(f"Updating preview permissions for resource: {resource.title}")
                    set_file_permissions(service, resource.preview_drive_file_id, make_public=True)

            except Exception as e:
                print(f"Error updating permissions for resource {resource.id}: {e}")

        print(f"Updated permissions for {updated_count} resources")

if __name__ == "__main__":
    update_resource_permissions()