"""
Check current course translations in database
"""
from yonca import create_app
app = create_app()
from yonca.models import ContentTranslation, Course, db

with app.app_context():
    courses = Course.query.all()
    
    print("=" * 100)
    print("CHECKING COURSE TRANSLATIONS")
    print("=" * 100)
    
    for course in courses[:3]:  # First 3 courses
        print(f"\nCourse ID {course.id}: {course.title}")
        print("-" * 100)
        
        # Check az translations
        az_title = ContentTranslation.query.filter_by(
            content_type='course',
            content_id=course.id,
            field_name='title',
            target_language='az'
        ).first()
        
        # Check ru translations
        ru_title = ContentTranslation.query.filter_by(
            content_type='course',
            content_id=course.id,
            field_name='title',
            target_language='ru'
        ).first()
        
        print(f"  Original (EN): {course.title}")
        print(f"  Azerbaijani:   {az_title.translated_text if az_title else 'NOT FOUND'}")
        print(f"  Russian:       {ru_title.translated_text if ru_title else 'NOT FOUND'}")
        
        if az_title and az_title.translated_text == course.title:
            print("  ⚠️  Azerbaijani is same as English!")
