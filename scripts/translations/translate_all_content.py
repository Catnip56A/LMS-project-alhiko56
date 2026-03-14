"""
Manual translation utility for dynamic content
Run this script to translate existing courses, resources, and home content
"""
from yonca import create_app
app = create_app()
from yonca.models import db, Course, Resource, HomeContent
from yonca.content_translator import (
    auto_translate_course,
    auto_translate_resource,
    auto_translate_home_content
)

def translate_all_courses():
    """Translate all courses"""
    print("\n" + "="*60)
    print("Translating All Courses")
    print("="*60)
    
    with app.app_context():
        courses = Course.query.all()
        print(f"\nFound {len(courses)} courses")
        
        for course in courses:
            try:
                auto_translate_course(course)
                db.session.commit()
                print(f"✓ Translated course: {course.title}")
            except Exception as e:
                db.session.rollback()
                print(f"✗ Error translating course {course.id}: {e}")


def translate_all_resources():
    """Translate all resources"""
    print("\n" + "="*60)
    print("Translating All Resources")
    print("="*60)
    
    with app.app_context():
        resources = Resource.query.all()
        print(f"\nFound {len(resources)} resources")
        
        for resource in resources:
            try:
                auto_translate_resource(resource)
                db.session.commit()
                print(f"✓ Translated resource: {resource.title}")
            except Exception as e:
                db.session.rollback()
                print(f"✗ Error translating resource {resource.id}: {e}")


def translate_all_home_content():
    """Translate all home content"""
    print("\n" + "="*60)
    print("Translating Home Content")
    print("="*60)
    
    with app.app_context():
        home_contents = HomeContent.query.all()
        print(f"\nFound {len(home_contents)} home content records")
        
        for home in home_contents:
            try:
                auto_translate_home_content(home)
                db.session.commit()
                print(f"✓ Translated home content {home.id}")
            except Exception as e:
                db.session.rollback()
                print(f"✗ Error translating home content {home.id}: {e}")


def main():
    """Translate all content"""
    print("\n" + "="*70)
    print("CONTENT TRANSLATION UTILITY")
    print("="*70)
    print("\nThis script will translate all existing content to Azerbaijani and Russian.")
    print("Forum translations are handled separately.")
    
    import sys
    if len(sys.argv) > 1:
        content_type = sys.argv[1].lower()
        if content_type == 'courses':
            translate_all_courses()
        elif content_type == 'resources':
            translate_all_resources()
        elif content_type == 'home':
            translate_all_home_content()
        else:
            print(f"\n⚠️  Unknown content type: {content_type}")
            print("Available options: courses, resources, home, all")
            return
    else:
        # Translate everything
        translate_all_courses()
        translate_all_resources()
        translate_all_home_content()
    
    print("\n" + "="*70)
    print("✓ Translation complete!")
    print("="*70)
    print("\nTranslations will now appear automatically when users change language.")
    print("Use {{ translate_field(...) }} and {{ translate_json(...) }} in templates.")
    print()


if __name__ == '__main__':
    main()
