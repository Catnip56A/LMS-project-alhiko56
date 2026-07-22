from lms import create_app, db
from lms.models import CourseContent, ContentView

app = create_app()
with app.app_context():
    # Check ContentView sample data
    views = ContentView.query.filter_by(content_type='course_content').limit(5).all()
    print("Sample ContentView records:")
    for v in views:
        print(f"  content_id={v.content_id}, user_id={v.user_id}, duration={v.viewing_duration}")
    
    # Check what CourseContent IDs and drive_file_ids look like
    contents = CourseContent.query.filter(
        CourseContent.drive_file_id.isnot(None),
        CourseContent.course_id == 1
    ).all()
    
    print("\nCourse content IDs vs drive_file_ids:")
    for c in contents:
        print(f"  id={c.id}, title={c.title}, drive_file_id={c.drive_file_id}")
    
    # Check if there's a mismatch: do ContentView records use CourseContent.id or drive_file_id?
    print("\nChecking for content_id matches:")
    for c in contents:
        matching = ContentView.query.filter_by(
            content_type='course_content',
            content_id=c.drive_file_id,
            user_id=1
        ).first()
        print(f"  drive_file_id={c.drive_file_id}: {'FOUND' if matching else 'NOT FOUND'}")
