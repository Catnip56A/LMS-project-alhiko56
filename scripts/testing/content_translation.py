"""
Test script for the automatic content translation system
This script demonstrates how content is automatically translated when created/updated
"""
from yonca import create_app
app = create_app()
from yonca.models import db, Course, Resource, HomeContent, ContentTranslation

def test_course_translation():
    """Test course auto-translation"""
    print("\n" + "="*60)
    print("Testing Course Auto-Translation")
    print("="*60)
    
    with app.app_context():
        # Create a test course
        course = Course(
            title="Web Development Fundamentals",
            description="Learn HTML, CSS, and JavaScript from scratch",
            page_welcome_title="Welcome to Web Development",
            page_subtitle="Master the basics of modern web development",
            page_description="This comprehensive course covers everything you need to start building websites."
        )
        
        db.session.add(course)
        db.session.commit()
        
        print(f"\n✓ Created course: {course.title}")
        print(f"  Course ID: {course.id}")
        
        # Check translations
        translations = ContentTranslation.query.filter_by(
            content_type='course',
            content_id=course.id
        ).all()
        
        print(f"\n📝 Auto-generated translations: {len(translations)}")
        
        # Group by language
        by_lang = {}
        for t in translations:
            if t.target_language not in by_lang:
                by_lang[t.target_language] = []
            by_lang[t.target_language].append(t)
        
        for lang, trans_list in by_lang.items():
            print(f"\n  {lang.upper()} translations ({len(trans_list)}):")
            for t in trans_list[:3]:  # Show first 3
                print(f"    • {t.field_name}: {t.translated_text[:60]}...")
        
        return course


def test_resource_translation():
    """Test resource auto-translation"""
    print("\n" + "="*60)
    print("Testing Resource Auto-Translation")
    print("="*60)
    
    with app.app_context():
        # Create a test resource
        resource = Resource(
            title="Python Programming Guide",
            description="A comprehensive guide to Python programming for beginners and intermediate learners"
        )
        
        db.session.add(resource)
        db.session.commit()
        
        print(f"\n✓ Created resource: {resource.title}")
        print(f"  Resource ID: {resource.id}")
        
        # Check translations
        translations = ContentTranslation.query.filter_by(
            content_type='resource',
            content_id=resource.id
        ).all()
        
        print(f"\n📝 Auto-generated translations: {len(translations)}")
        
        for t in translations:
            print(f"  • {t.field_name} ({t.target_language}): {t.translated_text}")
        
        return resource


def test_home_content_translation():
    """Test home content auto-translation"""
    print("\n" + "="*60)
    print("Testing Home Content Auto-Translation")
    print("="*60)
    
    with app.app_context():
        # Get or create home content
        home = HomeContent.query.first()
        
        if not home:
            home = HomeContent(
                welcome_title="Welcome to Yonca Learning Platform",
                subtitle="Your gateway to quality education and community learning",
                courses_section_title="Explore Our Courses",
                courses_section_description="Discover a wide range of courses designed to help you achieve your learning goals"
            )
            db.session.add(home)
            db.session.commit()
            print(f"\n✓ Created home content")
        else:
            # Update to trigger translation
            home.welcome_title = "Welcome to Yonca Learning Platform"
            home.subtitle = "Your gateway to quality education and community learning"
            db.session.commit()
            print(f"\n✓ Updated home content")
        
        print(f"  Home Content ID: {home.id}")
        
        # Check translations
        translations = ContentTranslation.query.filter_by(
            content_type='home_content',
            content_id=home.id
        ).all()
        
        print(f"\n📝 Auto-generated translations: {len(translations)}")
        
        # Group by language
        by_lang = {}
        for t in translations:
            if t.target_language not in by_lang:
                by_lang[t.target_language] = []
            by_lang[t.target_language].append(t)
        
        for lang, trans_list in by_lang.items():
            print(f"\n  {lang.upper()} translations ({len(trans_list)}):")
            for t in trans_list[:5]:  # Show first 5
                print(f"    • {t.field_name}: {t.translated_text[:60]}...")
        
        return home


def test_translation_retrieval():
    """Test retrieving translations using template helpers"""
    print("\n" + "="*60)
    print("Testing Translation Retrieval")
    print("="*60)
    
    from yonca.content_translator import get_translated_content
    
    with app.app_context():
        # Get a course
        course = Course.query.first()
        if not course:
            print("\n⚠️  No courses found. Run other tests first.")
            return
        
        print(f"\nOriginal course title: {course.title}")
        
        # Get Azerbaijani translation
        az_title = get_translated_content('course', course.id, 'title', course.title, 'az')
        print(f"Azerbaijani translation: {az_title}")
        
        # Get Russian translation
        ru_title = get_translated_content('course', course.id, 'title', course.title, 'ru')
        print(f"Russian translation: {ru_title}")
        
        # Get English (should return original)
        en_title = get_translated_content('course', course.id, 'title', course.title, 'en')
        print(f"English (original): {en_title}")


def show_translation_stats():
    """Show overall translation statistics"""
    print("\n" + "="*60)
    print("Translation Statistics")
    print("="*60)
    
    with app.app_context():
        # Count by content type
        from sqlalchemy import func
        
        stats = db.session.query(
            ContentTranslation.content_type,
            ContentTranslation.target_language,
            func.count(ContentTranslation.id).label('count')
        ).group_by(
            ContentTranslation.content_type,
            ContentTranslation.target_language
        ).all()
        
        if not stats:
            print("\n⚠️  No translations found yet.")
            return
        
        # Organize by content type
        by_type = {}
        for content_type, lang, count in stats:
            if content_type not in by_type:
                by_type[content_type] = {}
            by_type[content_type][lang] = count
        
        print()
        for content_type, langs in by_type.items():
            print(f"\n{content_type.upper()}:")
            for lang, count in langs.items():
                print(f"  • {lang}: {count} translations")


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("CONTENT TRANSLATION SYSTEM TEST")
    print("="*70)
    print("\nThis script tests the automatic content translation system.")
    print("Content will be automatically translated to Azerbaijani (az) and Russian (ru).")
    
    try:
        # Test course translation
        test_course_translation()
        
        # Test resource translation
        test_resource_translation()
        
        # Test home content translation
        test_home_content_translation()
        
        # Test translation retrieval
        test_translation_retrieval()
        
        # Show stats
        show_translation_stats()
        
        print("\n" + "="*70)
        print("✓ All tests completed successfully!")
        print("="*70)
        print("\nTo use translations in templates:")
        print("  {{ translate_field('course', course.id, 'title', course.title) }}")
        print("  {{ translate_json('home_content', home.id, 'features', home.features) }}")
        print("\nSee docs/CONTENT_TRANSLATION.md for more details.")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
