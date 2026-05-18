#!/usr/bin/env python3
"""
Script to list all viewing times per file for all users.
Usage: python scripts/view_times.py [--user USERNAME] [--content-type TYPE] [--limit N]
"""
import sys
import os
from datetime import datetime
from collections import defaultdict

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from yonca import create_app
from yonca.models import db, User, ContentView, CourseContent


def format_duration(seconds):
    """Format duration in seconds to human-readable format"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"{hours}h {remaining_minutes}m"


def get_content_name(content_type, content_id):
    """Get human-readable name for content"""
    if content_type == 'course_content':
        # Try matching by Integer PK first (old records), then by drive_file_id (new String records)
        try:
            content = CourseContent.query.get(int(content_id))
        except (ValueError, TypeError):
            content = None
        if not content:
            content = CourseContent.query.filter_by(drive_file_id=content_id).first()
        if content:
            return f"{content.title} (ID: {content_id})"
        return f"Course Content ID: {content_id}"
    else:
        return f"{content_type} ID: {content_id}"


def list_view_times(username=None, content_type=None, limit=None):
    """List viewing times per file for all users or specific user"""
    
    app = create_app()
    
    with app.app_context():
        # Base query - group by user, content_type, content_id
        query = db.session.query(
            ContentView.user_id,
            ContentView.content_type,
            ContentView.content_id,
            db.func.sum(ContentView.viewing_duration).label('total_duration'),
            db.func.count(ContentView.id).label('view_count'),
            db.func.max(ContentView.viewed_at).label('last_viewed')
        ).group_by(
            ContentView.user_id,
            ContentView.content_type,
            ContentView.content_id
        ).order_by(
            db.func.sum(ContentView.viewing_duration).desc()
        )
        
        # Apply filters
        if username:
            user = User.query.filter_by(username=username).first()
            if not user:
                print(f"❌ User '{username}' not found!")
                return False
            query = query.filter(ContentView.user_id == user.id)
        
        if content_type:
            query = query.filter(ContentView.content_type == content_type)
        
        if limit:
            query = query.limit(limit)
        
        results = query.all()
        
        if not results:
            print("📊 No viewing records found.")
            return True
        
        # Print header
        print("\n" + "="*80)
        print("📊 CONTENT VIEWING TIME REPORT")
        print("="*80)
        if username:
            print(f"👤 Filtered by user: {username}")
        if content_type:
            print(f"📁 Filtered by content type: {content_type}")
        if limit:
            print(f"🔢 Limited to: {limit} records")
        print("="*80)
        
        # Print results
        print(f"{'User':<20} {'Content Type':<15} {'Content ID':<10} {'Duration':<15} {'Views':<8} {'Last Viewed':<20}")
        print("-"*80)
        
        for result in results:
            user = User.query.get(result.user_id)
            username_display = user.username if user else f"User {result.user_id}"
            content_name = get_content_name(result.content_type, result.content_id)
            
            print(f"{username_display:<20} {result.content_type:<15} {result.content_id:<10} "
                  f"{format_duration(result.total_duration):<15} {result.view_count:<8} "
                  f"{result.last_viewed.strftime('%Y-%m-%d %H:%M') if result.last_viewed else 'N/A':<20}")
            print(f"  └─ {content_name}")
        
        # Print summary
        print("\n" + "="*80)
        print("📈 SUMMARY")
        print("="*80)
        
        total_views = sum(r.view_count for r in results)
        total_duration = sum(r.total_duration for r in results)
        unique_users = len(set(r.user_id for r in results))
        unique_content = len(set((r.content_type, r.content_id) for r in results))
        
        print(f"👥 Unique users: {unique_users}")
        print(f"📁 Unique content items: {unique_content}")
        print(f"👁️  Total views: {total_views}")
        print(f"⏱️  Total duration: {format_duration(total_duration)}")
        print("="*80 + "\n")
        
        return True


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='List viewing times per file for all users')
    parser.add_argument('--user', help='Filter by username')
    parser.add_argument('--content-type', help='Filter by content type (e.g., course_content)')
    parser.add_argument('--limit', type=int, help='Limit number of records')
    
    args = parser.parse_args()
    
    success = list_view_times(
        username=args.user,
        content_type=args.content_type,
        limit=args.limit
    )
    
    sys.exit(0 if success else 1)
